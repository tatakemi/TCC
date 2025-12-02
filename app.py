# (full file contents)
import flet as ft
import os
import threading
import socket
import json
import webbrowser
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

from models import User, LostAnimal, FoundReport, session_scope, session

# ---- Geocoding setup ----
geolocator = Nominatim(user_agent="siara_app_geocoder")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1, return_value_on_exception=None)
reverse_rate_limited = RateLimiter(geolocator.reverse, min_delay_seconds=1, return_value_on_exception=None)

# small in-memory caches
_geocode_cache = {}
_reverse_cache = {}

def geocode_address(text):
    if not text:
        return None, None
    key = text.strip().lower()
    if key in _geocode_cache:
        return _geocode_cache[key]
    try:
        loc = geocode(text, timeout=10)
        if loc:
            coords = (loc.latitude, loc.longitude)
            _geocode_cache[key] = coords
            return coords
    except Exception as e:
        print("Geocode error:", e)
    _geocode_cache[key] = (None, None)
    return None, None

def reverse_geocode(lat, lon):
    if lat is None or lon is None:
        return None
    key = f"{lat:.6f},{lon:.6f}"
    if key in _reverse_cache:
        return _reverse_cache[key]
    try:
        loc = reverse_rate_limited(f"{lat}, {lon}", exactly_one=True, timeout=10)
        if loc and getattr(loc, "address", None):
            address = loc.address
            _reverse_cache[key] = address
            return address
    except Exception as e:
        print("Reverse geocode error:", e)
    _reverse_cache[key] = None
    return None

# ---- Static map preview helper (OpenStreetMap static map service) ----
def build_static_map_url(lat, lon, zoom=15, width=600, height=300, marker="red-pushpin"):
    if lat is None or lon is None:
        return ""
    ts = int(time.time() * 1000)  # cache buster to force fresh image
    url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom={zoom}&size={width}x{height}&markers={lat},{lon},{marker}&ts={ts}"
    print("Preview URL:", url)
    return url

# ---- Map server globals and utilities ----
STATIC_DIR = Path(os.getcwd()) / "map_static"
STATIC_DIR.mkdir(exist_ok=True)

LAST_PICK = {"lat": None, "lon": None}   # updated by POST /pick

_httpd = None
_httpd_thread = None

def find_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

class MapHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/reports.json"):
            try:
                reports = []
                with session_scope() as s:
                    for a in s.query(LostAnimal).all():
                        reports.append({
                            "type": "Animal perdido",
                            "title": a.name,
                            "desc": f"{a.desc_animal or ''} ({a.lost_location or ''})",
                            "lat": a.latitude,
                            "lon": a.longitude
                        })
                    for r in s.query(FoundReport).all():
                        reports.append({
                            "type": "found",
                            "title": r.species or "Animal encontrado",
                            "desc": f"{r.found_description or ''} ({r.found_location or ''})",
                            "lat": r.latitude,
                            "lon": r.longitude
                        })
                data = json.dumps(reports).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
            return
        else:
            return super().do_GET()

    def do_POST(self):
        global LAST_PICK
        if self.path == "/pick":
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode('utf-8'))
                lat = payload.get("lat")
                lon = payload.get("lon")
                if lat is not None and lon is not None:
                    LAST_PICK["lat"] = float(lat)
                    LAST_PICK["lon"] = float(lon)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK")
                    return
                else:
                    raise ValueError("lat/lon missing")
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
                return
        else:
            self.send_response(404)
            self.end_headers()
            return

def start_map_server(port):
    global _httpd, _httpd_thread
    if _httpd is not None:
        return
    handler_class = partial(MapHandler, directory=str(STATIC_DIR))
    _httpd = HTTPServer(("127.0.0.1", port), handler_class)
    def serve():
        try:
            _httpd.serve_forever()
        except Exception as e:
            print("Map server stopped:", e)
    _httpd_thread = threading.Thread(target=serve, daemon=True)
    _httpd_thread.start()
    print(f"Map server started at http://127.0.0.1:{port}/")

def stop_map_server():
    global _httpd
    if _httpd:
        _httpd.shutdown()
        _httpd = None

MAP_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
<style>html,body,#map{height:100%;margin:0;padding:0}</style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<script>
async function loadReports() {
    try {
        const res = await fetch('/reports.json');
        return await res.json();
    } catch (e) {
        console.error('Failed to load reports', e);
        return [];
    }
}

function buildMap(reports) {
    var map = L.map('map').setView([0,0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    var group = L.featureGroup();
    reports.forEach(r=>{
        if (!r.lat || !r.lon) return;
        var color = (r.type === 'lost') ? 'red' : 'green';
        var marker = L.circleMarker([r.lat, r.lon], {
            radius: 8,
            color: color,
            fillColor: color,
            fillOpacity: 0.9
        }).bindPopup(`<b>${r.title || ''}</b><br>${r.desc || ''}`);
        group.addLayer(marker);
    });
    group.addTo(map);
    if (group.getLayers().length > 0) {
        map.fitBounds(group.getBounds().pad(0.2));
    }

    map.on('click', async function(e) {
        const lat = e.latlng.lat, lon = e.latlng.lng;
        const payload = {lat: lat, lon: lon};
        try {
            await fetch('/pick', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            alert(`Picked coords: ${lat.toFixed(6)}, ${lon.toFixed(6)}\\nReturn to the app and press "Fetch picked coords" to import them.`);
        } catch (err) {
            alert('Failed to send picked coords: ' + err);
        }
    });
}

(async function() {
    const reports = await loadReports();
    buildMap(reports);
})();
</script>
</body>
</html>
"""

def write_base_map_html():
    p = STATIC_DIR / "map.html"
    p.write_text(MAP_HTML, encoding="utf-8")

# ---- Flet UI ----
def main(page: ft.Page):
    page.title = "SIARA"
    page.window_width = 1000
    page.window_height = 700
    page.padding = 20

    state = {"current_user": None, "map_port": None}

    write_base_map_html()
    if state.get("map_port") is None:
        port = find_free_port()
        state["map_port"] = port
        start_map_server(port)

    # helper: user feedback snackbar
    def show_snack(message: str, success: bool = True):
        color = ft.Colors.GREEN if success else ft.Colors.RED
        page.snack_bar = ft.SnackBar(ft.Text(message), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def show_login(e=None):
        page.controls.clear()
        username = ft.TextField(label="Usuário")
        password = ft.TextField(label="Senha", password=True, can_reveal_password=True)
        msg = ft.Text("", color=ft.Colors.RED)

        def do_login(ev):
            uname = username.value.strip()
            pwd = password.value or ""
            if not uname:
                msg.value = "Insira o nome de usuário"
                page.update()
                return
            with session_scope() as s:
                user = s.query(User).filter_by(username=uname).first()
                if user and user.check_password(pwd):
                    state["current_user"] = {"id": user.id, "username": user.username}
                    show_home()
                else:
                    msg.value = "Usuário ou senha inválidos"
                    page.update()

        page.add(ft.Text("Login", size=20), username, password,
                 ft.Row([ft.ElevatedButton("Log-in", on_click=do_login),
                         ft.TextButton("Não tenho uma conta", on_click=show_register)]), msg)

    def show_register(e=None):
        page.controls.clear()
        username = ft.TextField(label="Usuário")
        contact = ft.TextField(label="Contato (telefone/email)")
        password = ft.TextField(label="Senha", password=True, can_reveal_password=True)
        password2 = ft.TextField(label="Confirmar senha", password=True, can_reveal_password=True)
        msg = ft.Text("", color=ft.Colors.RED)

        def do_register(ev):
            uname = username.value.strip()
            pwd = password.value or ""
            pwd2 = password2.value or ""
            if not uname:
                msg.value = "Insira o nome de usuário"
                page.update()
                return
            if pwd != pwd2 or not pwd:
                msg.value = "As senhas não coincidem ou estão vazias"
                page.update()
                return
            with session_scope() as s:
                existing = s.query(User).filter_by(username=uname).first()
                if existing:
                    msg.value = "Usuário já existe"
                    page.update()
                    return
                u = User(username=uname, contact=contact.value.strip())
                u.set_password(pwd)
                s.add(u)
                s.flush()
                state["current_user"] = {"id": u.id, "username": u.username}
            show_snack("Account created; you are now logged in.")
            show_home()

    def show_home(e=None):
        page.controls.clear()
        cur = state["current_user"]
        if not cur:
            show_login()
            return
        header = ft.Text(f"Welcome, {cur['username']}", size=18)
        btn_lost = ft.ElevatedButton("Registrar animal perdido", on_click=show_lost_registration)
        btn_found = ft.ElevatedButton("Registrar animal encontrado", on_click=show_found_registration)
        btn_my = ft.ElevatedButton("Meus posts", on_click=show_my_posts)
        btn_map = ft.ElevatedButton("Abrir mapa (browser)", on_click=show_map)
        btn_logout = ft.TextButton("Sair", on_click=do_logout)

        lost_list = ft.ListView(expand=True, spacing=10)
        found_list = ft.ListView(expand=True, spacing=10)

        with session_scope() as s:
            for a in s.query(LostAnimal).order_by(LostAnimal.id.desc()).all():
                owner_name = a.owner.username if a.owner else "—"
                info = f"Tutor: {owner_name}\nOnde foi perdido: {a.lost_location or ''}\nDescrição: {a.desc_animal or ''}"
                if a.latitude and a.longitude:
                    info += f"\nCoordenadas: {a.latitude:.6f}, {a.longitude:.6f}"
                lost_list.controls.append(ft.Container(ft.ListTile(title=ft.Text(a.name), subtitle=ft.Text(info)), bgcolor=ft.Colors.BLACK12, padding=12, margin=3, border_radius=8))
            for r in s.query(FoundReport).order_by(FoundReport.id.desc()).all():
                finder_name = r.finder.username if r.finder else "—"
                info = f"Quem encontrou: {finder_name}\nOnde foi encontrado: {r.found_location or ''}\nDescrição: {r.found_description or ''}"
                if r.latitude and r.longitude:
                    info += f"\nCoordenadas: {r.latitude:.6f}, {r.longitude:.6f}"
                found_list.controls.append(ft.Container(ft.ListTile(title=ft.Text(r.species or "Animal encontrado"), subtitle=ft.Text(info)), bgcolor=ft.Colors.INDIGO_ACCENT, padding=12, margin=3, border_radius=8))

        page.add(header, ft.Row([btn_lost, btn_found, btn_my, btn_map, btn_logout]), ft.Text("Animais perdidos:"), lost_list, ft.Text("Animais encontrados:"), found_list)

    def do_logout(e):
        state["current_user"] = None
        show_login()

    # ---------- My posts (view / edit / delete) ----------
    def show_my_posts(e=None):
        page.controls.clear()
        cur = state["current_user"]
        if not cur:
            show_login()
            return

        page.add(ft.Text("My posts", size=18))
        my_lost_list = ft.ListView(expand=True, spacing=8)
        my_found_list = ft.ListView(expand=True, spacing=8)

        # load data inside a session and convert to plain dicts to avoid detached-instance errors
        with session_scope() as s:
            losts_rows = s.query(LostAnimal).filter_by(owner_id=cur["id"]).order_by(LostAnimal.id.desc()).all()
            founds_rows = s.query(FoundReport).filter_by(finder_id=cur["id"]).order_by(FoundReport.id.desc()).all()

            losts = [{
                "id": a.id,
                "name": a.name,
                "lost_location": a.lost_location,
                "desc_animal": a.desc_animal,
                "latitude": a.latitude,
                "longitude": a.longitude
            } for a in losts_rows]

            founds = [{
                "id": r.id,
                "species": r.species,
                "found_location": r.found_location,
                "found_description": r.found_description,
                "latitude": r.latitude,
                "longitude": r.longitude
            } for r in founds_rows]

        if not losts and not founds:
            page.add(ft.Text("Você não tem posts ainda."))
            page.add(ft.Row([ft.ElevatedButton("Back", on_click=show_home)]))
            return

        # build lost list items
        for ld in losts:
            info = f"{ld['name']} — {ld['lost_location'] or ''}\n{ld['desc_animal'] or ''}"
            if ld['latitude'] and ld['longitude']:
                info += f"\nCoords: {ld['latitude']:.6f}, {ld['longitude']:.6f}"
            item = ft.Container(
                ft.Row([
                    ft.Column([ft.Text(ld['name'], weight=ft.FontWeight.BOLD), ft.Text(info)], expand=True),
                    ft.Column([
                        ft.ElevatedButton("Editar", on_click=lambda e, aid=ld['id']: show_edit_lost(aid)),
                        ft.TextButton("Deletar", on_click=lambda e, aid=ld['id']: confirm_delete_lost(aid))
                    ])
                ]),
                bgcolor=ft.Colors.BLACK12,
                padding=12,
                margin=3,
                border_radius=8
            )
            my_lost_list.controls.append(item)

        # build found list items
        for fd in founds:
            info = f"{fd['species'] or 'Animal encontrado'} — {fd['found_location'] or ''}\n{fd['found_description'] or ''}"
            if fd['latitude'] and fd['longitude']:
                info += f"\nCoords: {fd['latitude']:.6f}, {fd['longitude']:.6f}"
            item = ft.Container(
                ft.Row([
                    ft.Column([ft.Text(fd['species'] or "Animal encontrado", weight=ft.FontWeight.BOLD), ft.Text(info)], expand=True),
                    ft.Column([
                        ft.ElevatedButton("Edit", on_click=lambda e, rid=fd['id']: show_edit_found(rid)),
                        ft.TextButton("Delete", on_click=lambda e, rid=fd['id']: confirm_delete_found(rid))
                    ])
                ]),
                bgcolor=ft.Colors.INDIGO_ACCENT,
                padding=12,
                margin=3,
                border_radius=8
            )
            my_found_list.controls.append(item)

        page.add(ft.Text("Meus animais perdidos"), my_lost_list, ft.Text("Animais que encontrei"), my_found_list, ft.Row([ft.ElevatedButton("Voltar", on_click=show_home)]))

    # Edit lost
    def show_edit_lost(lost_id):
        page.controls.clear()
        cur = state["current_user"]
        if not cur:
            show_login()
            return

        # load scalar values inside session and close session
        with session_scope() as s:
            a = s.query(LostAnimal).filter_by(id=lost_id, owner_id=cur["id"]).first()
            if not a:
                show_snack("Registro não encontrado", success=False)
                show_my_posts()
                return
            a_data = {
                "id": a.id,
                "name": a.name,
                "species": a.species,
                "lost_location": a.lost_location,
                "desc_animal": a.desc_animal,
                "contact": a.contact,
                "latitude": a.latitude,
                "longitude": a.longitude
            }

        name = ft.TextField(label="Nome do animal", value=a_data["name"] or "")
        species = ft.TextField(label="Espécie (opcional)", value=a_data["species"] or "")
        location = ft.TextField(label="Local", value=a_data["lost_location"] or "")
        desc = ft.TextField(label="Descrição (opcional)", value=a_data["desc_animal"] or "")
        contact = ft.TextField(label="Contato (opcional)", value=a_data["contact"] or "")
        lat_field = ft.TextField(label="Latitude (opcional)", value=f"{a_data['latitude']:.6f}" if a_data['latitude'] is not None else "")
        lon_field = ft.TextField(label="Longitude (opcional)", value=f"{a_data['longitude']:.6f}" if a_data['longitude'] is not None else "")
        preview_image = ft.Image(src="", width=600, height=300)
        preview_address = ft.Text("", selectable=True)
        msg = ft.Text("")

        def update_preview_from_fields():
            try:
                if lat_field.value.strip() and lon_field.value.strip():
                    lat = float(lat_field.value.strip()); lon = float(lon_field.value.strip())
                    preview_image.src = build_static_map_url(lat, lon)
                    preview_address.value = reverse_geocode(lat, lon) or "Endereço não encontrado"
                else:
                    preview_image.src = ""
                    preview_address.value = ""
            except Exception:
                preview_image.src = ""
                preview_address.value = ""
            try:
                preview_image.update()
            except:
                pass
            try:
                preview_address.update()
            except:
                pass
            page.update()

        def do_update(ev):
            if not name.value.strip():
                msg.value = "Nome é obrigatório"
                page.update()
                return
            try:
                lat = float(lat_field.value.strip()) if lat_field.value.strip() else None
                lon = float(lon_field.value.strip()) if lon_field.value.strip() else None
            except:
                msg.value = "Coordenadas inválidas"
                page.update()
                return
            with session_scope() as s:
                obj = s.query(LostAnimal).filter_by(id=lost_id, owner_id=cur["id"]).first()
                if not obj:
                    show_snack("Registro não encontrado para alterar", success=False)
                    show_my_posts()
                    return
                obj.name = name.value.strip()
                obj.species = species.value.strip() or None
                obj.lost_location = location.value.strip() or None
                obj.desc_animal = desc.value.strip() or None
                obj.contact = contact.value.strip() or None
                obj.latitude = lat
                obj.longitude = lon
                s.add(obj)
            show_snack("Registro atualizado")
            show_my_posts()

        page.add(ft.Text("Editar Registro de animal perdido", size=18),
                 name, species, location, desc, contact,
                 ft.Row([lat_field, lon_field]),
                 ft.Row([ft.ElevatedButton("Atualizar mapa", on_click=lambda e: update_preview_from_fields()),
                         ft.ElevatedButton("Salvar mudanças", on_click=do_update),
                         ft.TextButton("Cancelar", on_click=lambda e: show_my_posts())]),
                 preview_image, preview_address, msg)

        # initial preview
        update_preview_from_fields()

    # Edit found
    def show_edit_found(found_id):
        page.controls.clear()
        cur = state["current_user"]
        if not cur:
            show_login()
            return

        # load scalar values inside session and close session
        with session_scope() as s:
            r = s.query(FoundReport).filter_by(id=found_id, finder_id=cur["id"]).first()
            if not r:
                show_snack("Registro não encontrado", success=False)
                show_my_posts()
                return
            r_data = {
                "id": r.id,
                "species": r.species,
                "found_location": r.found_location,
                "found_date": r.found_date,
                "found_description": r.found_description,
                "latitude": r.latitude,
                "longitude": r.longitude
            }

        species = ft.TextField(label="Espécia (opcional)", value=r_data["species"] or "")
        location = ft.TextField(label="Local", value=r_data["found_location"] or "")
        date = ft.TextField(label="Data (opcional)", value=r_data["found_date"] or "")
        desc = ft.TextField(label="Descrição", value=r_data["found_description"] or "")
        lat_field = ft.TextField(label="Latitude (opcional)", value=f"{r_data['latitude']:.6f}" if r_data['latitude'] is not None else "")
        lon_field = ft.TextField(label="Longitude (opcional)", value=f"{r_data['longitude']:.6f}" if r_data['longitude'] is not None else "")
        preview_image = ft.Image(src="", width=600, height=300)
        preview_address = ft.Text("", selectable=True)
        msg = ft.Text("")

        def update_preview_from_fields():
            try:
                if lat_field.value.strip() and lon_field.value.strip():
                    lat = float(lat_field.value.strip()); lon = float(lon_field.value.strip())
                    preview_image.src = build_static_map_url(lat, lon)
                    preview_address.value = reverse_geocode(lat, lon) or "Endereço não encontrado"
                else:
                    preview_image.src = ""
                    preview_address.value = ""
            except Exception:
                preview_image.src = ""
                preview_address.value = ""
            try:
                preview_image.update()
            except:
                pass
            try:
                preview_address.update()
            except:
                pass
            page.update()

        def do_update(ev):
            try:
                lat = float(lat_field.value.strip()) if lat_field.value.strip() else None
                lon = float(lon_field.value.strip()) if lon_field.value.strip() else None
            except:
                msg.value = "Coordenadas inválidas"
                page.update()
                return
            with session_scope() as s:
                obj = s.query(FoundReport).filter_by(id=found_id, finder_id=cur["id"]).first()
                if not obj:
                    show_snack("Registro não encontrado para alterar", success=False)
                    show_my_posts()
                    return
                obj.species = species.value.strip() or None
                obj.found_location = location.value.strip() or None
                obj.found_date = date.value.strip() or None
                obj.found_description = desc.value.strip() or None
                obj.latitude = lat
                obj.longitude = lon
                s.add(obj)
            show_snack("Found report updated.")
            show_my_posts()

        page.add(ft.Text("Edit Found Report", size=18),
                 species, location, date, desc,
                 ft.Row([lat_field, lon_field]),
                 ft.Row([ft.ElevatedButton("Atualizar mapa", on_click=lambda e: update_preview_from_fields()),
                         ft.ElevatedButton("Salvar mudanças", on_click=do_update),
                         ft.TextButton("Cancelar", on_click=lambda e: show_my_posts())]),
                 preview_image, preview_address, msg)

        update_preview_from_fields()

    # Delete confirmation and handlers
    def confirm_delete_lost(lost_id):
        dlg = ft.AlertDialog(
            title=ft.Text("Deletar registro de animal perdido?"),
            content=ft.Text("Esta ação não pode ser desfeita."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: close_dialog()),
                ft.ElevatedButton("Deletar", bgcolor=ft.Colors.RED, on_click=lambda e: do_delete_lost(lost_id))
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    def close_dialog():
        # close and clear any open dialog
        if getattr(page, "dialog", None):
            try:
                page.dialog.open = False
            except Exception:
                pass
            page.dialog = None
            page.update()

    def confirm_delete_lost(lost_id):
        # Use a wrapper so we capture the id correctly
        def on_delete_click(e, lid=lost_id):
            _do_delete_lost(lid)

        dlg = ft.AlertDialog(
            title=ft.Text("Deletar registro de animal perdido?"),
            content=ft.Text("Esta ação não pode ser desfeita."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: close_dialog()),
                ft.ElevatedButton("Deletar", bgcolor=ft.Colors.RED, on_click=on_delete_click)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    def _do_delete_lost(lost_id):
        # internal: perform deletion in a fresh session and refresh UI
        close_dialog()
        cur = state.get("current_user")
        if not cur:
            show_snack("Você precisa estar logado para deletar posts", success=False)
            show_login()
            return

        try:
            with session_scope() as s:
                # load by primary key and verify ownership
                obj = s.get(LostAnimal, int(lost_id))
                if not obj or obj.owner_id != cur["id"]:
                    show_snack("Registro não encontrado", success=False)
                    return
                s.delete(obj)
            show_snack("Registro deletado.")
        except Exception as ex:
            print("Error deleting lost report:", ex)
            show_snack("Failed to delete lost report.", success=False)

        show_my_posts()

    def confirm_delete_found(found_id):
        def on_delete_click(e, fid=found_id):
            _do_delete_found(fid)

        dlg = ft.AlertDialog(
            title=ft.Text("Deletar registro de animal encontrado?"),
            content=ft.Text("Esta ação não pode ser desfeita."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: close_dialog()),
                ft.ElevatedButton("Deletar", bgcolor=ft.Colors.RED, on_click=on_delete_click)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    def _do_delete_found(found_id):
        close_dialog()
        cur = state.get("current_user")
        if not cur:
            show_snack("Você precisa estar logado para deletar posts", success=False)
            show_login()
            return

        try:
            with session_scope() as s:
                obj = s.get(FoundReport, int(found_id))
                if not obj or obj.finder_id != cur["id"]:
                    show_snack("Registro não encontrado.", success=False)
                    return
                s.delete(obj)
            show_snack("Registro deletado.")
        except Exception as ex:
            print("Error deleting found report:", ex)
            show_snack("Failed to delete found report.", success=False)

        show_my_posts()

    def confirm_delete_found(found_id):
        dlg = ft.AlertDialog(
            title=ft.Text("Deletar registro de animal encontrado?"),
            content=ft.Text("Esta ação não pode ser desfeita."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: close_dialog()),
                ft.ElevatedButton("Delete", bgcolor=ft.Colors.RED, on_click=lambda e: do_delete_found(found_id))
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    def do_delete_found(found_id):
        close_dialog()
        cur = state["current_user"]
        with session_scope() as s:
            obj = s.query(FoundReport).filter_by(id=found_id, finder_id=cur["id"]).first()
            if not obj:
                show_snack("Registro não encontrado", success=False)
                show_my_posts()
                return
            s.delete(obj)
        show_snack("Registro deletado.")
        show_my_posts()

    def close_dialog():
        if getattr(page, "dialog", None):
            page.dialog.open = False
            page.update()

    # ---------- Lost / Found registration (unchanged flow but improve confirmations) ----------
    def show_lost_registration(e=None):
        page.controls.clear()
        cur = state["current_user"]
        if not cur:
            show_login()
            return
        name = ft.TextField(label="Nome do animal")
        species = ft.TextField(label="Espécie (opcional)")
        location = ft.TextField(label="Onde foi perdido (endereço ou descrição)")
        desc = ft.TextField(label="Descrição do animal (opcional)")
        contact = ft.TextField(label="Contato (opcional)")
        lat_field = ft.TextField(label="Latitude (opcional)")
        lon_field = ft.TextField(label="Longitude (opcional)")
        msg = ft.Text("")

        preview_image = ft.Image(src="", width=600, height=300)
        preview_address = ft.Text("", selectable=True)

        def update_preview_from_fields():
            try:
                if lat_field.value.strip() and lon_field.value.strip():
                    lat = float(lat_field.value.strip()); lon = float(lon_field.value.strip())
                    preview_image.src = build_static_map_url(lat, lon)
                    preview_address.value = reverse_geocode(lat, lon) or "No address found for these coordinates."
                else:
                    preview_image.src = ""
                    preview_address.value = ""
            except Exception:
                preview_image.src = ""
                preview_address.value = ""
            try:
                preview_image.update()
            except:
                pass
            try:
                preview_address.update()
            except:
                pass
            page.update()

        def do_register_lost(ev):
            if not name.value.strip():
                msg.value = "Nome é obrigatório"
                page.update()
                return
            # if lat/lon provided use them; otherwise try geocoding
            lat = None; lon = None
            if lat_field.value.strip() and lon_field.value.strip():
                try:
                    lat = float(lat_field.value.strip())
                    lon = float(lon_field.value.strip())
                except:
                    msg.value = "Formato de coordenadas inválido"
                    page.update()
                    return
            else:
                lat, lon = geocode_address(location.value.strip())

            with session_scope() as s:
                la = LostAnimal(
                    name=name.value.strip(),
                    species=species.value.strip() or None,
                    lost_location=location.value.strip() or None,
                    desc_animal=desc.value.strip() or None,
                    contact=contact.value.strip() or None,
                    owner_id=cur["id"],
                    latitude=lat,
                    longitude=lon
                )
                s.add(la)
            show_snack("Animal perdido registrado.")
            # clear form fields
            name.value = species.value = location.value = desc.value = contact.value = ""
            lat_field.value = lon_field.value = ""
            update_preview_from_fields()
            page.update()

        def fetch_picked_coords(ev):
            lat = LAST_PICK.get("lat")
            lon = LAST_PICK.get("lon")
            if lat is None or lon is None:
                msg.value = "Coordenadas não selecionadas ainda — clique no mapa primeiro."
            else:
                lat_field.value = f"{lat:.6f}"
                lon_field.value = f"{lon:.6f}"
                msg.value = "Coordenadas importadas para o formulário."
                # automatically refresh preview and reverse-geocode
                update_preview_from_fields()
            page.update()

        page.add(ft.Text("Register Lost Animal", size=18),
                 name, species, location, desc, contact,
                 ft.Row([lat_field, lon_field]),
                 ft.Row([ft.ElevatedButton("Atualizar coordenadas selecionadas", on_click=fetch_picked_coords),
                         ft.ElevatedButton("Atualizar mapa", on_click=lambda e: (update_preview_from_fields())),
                         ft.ElevatedButton("Salvar", on_click=do_register_lost),
                         ft.TextButton("Voltar", on_click=show_home)]),
                 preview_image,
                 preview_address,
                 msg)

    def show_found_registration(e=None):
        page.controls.clear()
        cur = state["current_user"]
        if not cur:
            show_login()
            return
        species = ft.TextField(label="Epécie (opcional)")
        location = ft.TextField(label="Onde foi encontrado (endereço ou descrição)")
        date = ft.TextField(label="Data (opcional)")
        desc = ft.TextField(label="Descrição do animal")
        lat_field = ft.TextField(label="Latitude (opcional)")
        lon_field = ft.TextField(label="Longitude (opcional)")
        msg = ft.Text("")

        preview_image = ft.Image(src="", width=600, height=300)
        preview_address = ft.Text("", selectable=True)

        def update_preview_from_fields():
            try:
                if lat_field.value.strip() and lon_field.value.strip():
                    lat = float(lat_field.value.strip()); lon = float(lon_field.value.strip())
                    preview_image.src = build_static_map_url(lat, lon)
                    preview_address.value = reverse_geocode(lat, lon) or "No address found for these coordinates."
                else:
                    preview_image.src = ""
                    preview_address.value = ""
            except Exception:
                preview_image.src = ""
                preview_address.value = ""
            try:
                preview_image.update()
            except:
                pass
            try:
                preview_address.update()
            except:
                pass
            page.update()

        def do_register_found(ev):
            lat = None; lon = None
            if lat_field.value.strip() and lon_field.value.strip():
                try:
                    lat = float(lat_field.value.strip())
                    lon = float(lon_field.value.strip())
                except:
                    msg.value = "Formato de coordenadas inválido"
                    page.update()
                    return
            else:
                lat, lon = geocode_address(location.value.strip())

            with session_scope() as s:
                fr = FoundReport(
                    species=species.value.strip() or None,
                    found_location=location.value.strip() or None,
                    found_date=date.value.strip() or None,
                    found_description=desc.value.strip() or None,
                    finder_id=cur["id"],
                    latitude=lat,
                    longitude=lon
                )
                s.add(fr)
            show_snack("Registro de animal encontrado salvo.")
            # clear fields
            species.value = location.value = date.value = desc.value = ""
            lat_field.value = lon_field.value = ""
            update_preview_from_fields()
            page.update()

        def fetch_picked_coords(ev):
            lat = LAST_PICK.get("lat")
            lon = LAST_PICK.get("lon")
            if lat is None or lon is None:
                msg.value = "Coordenadas não selecionadas ainda — clique no mapa primeiro."
            else:
                lat_field.value = f"{lat:.6f}"
                lon_field.value = f"{lon:.6f}"
                msg.value = "Coordenadas importadas para o formulário."
                update_preview_from_fields()
            page.update()

        page.add(ft.Text("Registrar animal encontrado", size=18),
                 species, location, date, desc,
                 ft.Row([lat_field, lon_field]),
                 ft.Row([ft.ElevatedButton("Atualizar coordenadas selecionadas", on_click=fetch_picked_coords),
                         ft.ElevatedButton("Atualizar mapa", on_click=lambda e: (update_preview_from_fields())),
                         ft.ElevatedButton("Salvar", on_click=do_register_found),
                         ft.TextButton("Voltar", on_click=show_home)]),
                 preview_image,
                 preview_address,
                 msg)

    def show_map(e=None):
        port = state["map_port"]
        map_url = f"http://127.0.0.1:{port}/map.html"
        try:
            webbrowser.open(map_url)
        except Exception as ex:
            print("Failed to open browser:", ex)
        page.controls.clear()
        page.add(ft.Text("Mapa aberto no seu navegador", size=18),
                 ft.Text("Clique no mapa, retorne ao app e então lique em 'atualizar coordenadas'", selectable=True),
                 ft.Row([ft.ElevatedButton("Voltar", on_click=show_home),
                         ft.ElevatedButton("Abrir mapa no navegador", on_click=lambda e: webbrowser.open(map_url))]),
                 ft.Text(f"Map URL: {map_url}", selectable=True))

    # start UI
    show_login()

if __name__ == "__main__":
    ft.app(target=main)