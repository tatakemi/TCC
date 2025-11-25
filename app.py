import flet as ft
from models import User, LostAnimal, FoundReport, session_scope, session

def main(page: ft.Page):
    page.title = "SIARA"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.window_width = 900
    page.window_height = 700
    page.window_resizable = True
    page.padding = 20

    state = {"current_user": None}

    # ------- UI helpers -------
    def info_banner(text, color=ft.Colors.GREEN):
        return ft.Container(ft.Text(text), bgcolor=color, padding=10, alignment=ft.alignment.center)

    # ------- Navigation / views -------
    def show_login(e=None):
        page.controls.clear()

        txt = ft.Text("Login", size=20)
        username = ft.TextField(label="Username")
        password = ft.TextField(label="Password", password=True, can_reveal_password=True)
        msg = ft.Text("", color=ft.Colors.RED)

        def do_login(ev):
            uname = username.value.strip()
            pwd = password.value or ""
            if not uname:
                msg.value = "Enter username"
                page.update()
                return
            with session_scope() as s:
                user = s.query(User).filter_by(username=uname).first()
                if user and user.check_password(pwd):
                    state["current_user"] = {"id": user.id, "username": user.username}
                    show_home()
                else:
                    msg.value = "Invalid username or password"
                    page.update()

        btn_login = ft.ElevatedButton("Login", on_click=do_login)
        btn_register = ft.TextButton("Create an account", on_click=show_register)
        page.add(txt, username, password, ft.Row([btn_login, btn_register]), msg)

    def show_register(e=None):
        page.controls.clear()
        txt = ft.Text("Register", size=20)
        username = ft.TextField(label="Username")
        contact = ft.TextField(label="Contact (phone or email)")
        password = ft.TextField(label="Password", password=True, can_reveal_password=True)
        password2 = ft.TextField(label="Confirm Password", password=True, can_reveal_password=True)
        msg = ft.Text("", color=ft.Colors.RED)

        def do_register(ev):
            uname = username.value.strip()
            pwd = password.value or ""
            pwd2 = password2.value or ""
            if not uname:
                msg.value = "Enter username"
                page.update()
                return
            if pwd != pwd2 or not pwd:
                msg.value = "Passwords do not match or empty"
                page.update()
                return
            with session_scope() as s:
                existing = s.query(User).filter_by(username=uname).first()
                if existing:
                    msg.value = "Username already exists"
                    page.update()
                    return
                u = User(username=uname, contact=contact.value.strip())
                u.set_password(pwd)
                s.add(u)
                s.flush()  # ensure id is assigned
                state["current_user"] = {"id": u.id, "username": u.username}
            show_home()

        btn_back = ft.TextButton("Back to login", on_click=show_login)
        btn_create = ft.ElevatedButton("Create account", on_click=do_register)
        page.add(txt, username, contact, password, password2, ft.Row([btn_create, btn_back]), msg)

    def show_home(e=None):
        page.controls.clear()
        cur = state["current_user"]
        if not cur:
            show_login()
            return
        header = ft.Text(f"Welcome, {cur['username']}", size=18)
        btn_lost = ft.ElevatedButton("Register Lost Animal", on_click=show_lost_registration)
        btn_found = ft.ElevatedButton("Register Found Animal", on_click=show_found_registration)
        btn_logout = ft.TextButton("Logout", on_click=do_logout)

        # list lost animals
        lost_list = ft.ListView(expand=True, spacing=10)
        found_list = ft.ListView(expand=True, spacing=10)

        with session_scope() as s:
            for a in s.query(LostAnimal).order_by(LostAnimal.id.desc()).all():
                owner_name = a.owner.username if a.owner else "—"
                lost_list.controls.append(
                    ft.Container(
                        ft.ListTile(
                            title=ft.Text(a.name),
                            subtitle=ft.Text(f"Owner: {owner_name}\nLost at: {a.lost_location}\nDesc: {a.desc_animal or ''}")
                        ),
                        bgcolor=ft.Colors.BLACK12,
                        padding=12,
                        margin=3,
                        border_radius=8
                    )
                )
            for r in s.query(FoundReport).order_by(FoundReport.id.desc()).all():
                finder_name = r.finder.username if r.finder else "—"
                found_list.controls.append(
                    ft.Container(
                        ft.ListTile(
                            title=ft.Text(r.species or "Found animal"),
                            subtitle=ft.Text(f"Finder: {finder_name}\nFound at: {r.found_location}\nDesc: {r.found_description or ''}\nDate: {r.found_date or ''}")
                        ),
                        bgcolor=ft.Colors.BLACK12,
                        padding=12,
                        margin=3,
                        border_radius=8
                    )
                )

        page.add(header, ft.Row([btn_lost, btn_found, btn_logout]), ft.Text("Lost animals:"), lost_list, ft.Text("Found reports:"), found_list)

    def do_logout(e):
        state["current_user"] = None
        show_login()

    def show_lost_registration(e=None):
        page.controls.clear()
        cur = state["current_user"]
        if not cur:
            show_login()
            return
        txt = ft.Text("Register Lost Animal", size=18)
        name = ft.TextField(label="Animal name")
        species = ft.TextField(label="Species (optional)")
        location = ft.TextField(label="Location where it was lost")
        desc = ft.TextField(label="Description (optional)")
        contact = ft.TextField(label="Contact (optional)")
        msg = ft.Text("")

        def do_register_lost(ev):
            if not name.value.strip():
                msg.value = "Name is required"
                page.update()
                return
            with session_scope() as s:
                la = LostAnimal(
                    name=name.value.strip(),
                    species=species.value.strip() or None,
                    lost_location=location.value.strip() or None,
                    desc_animal=desc.value.strip() or None,
                    contact=contact.value.strip() or None,
                    owner_id=cur["id"]
                )
                s.add(la)
            msg.value = "Lost animal registered."
            page.update()

        btn_back = ft.TextButton("Back", on_click=show_home)
        btn_save = ft.ElevatedButton("Save lost animal", on_click=do_register_lost)
        page.add(txt, name, species, location, desc, contact, ft.Row([btn_save, btn_back]), msg)

    def show_found_registration(e=None):
        page.controls.clear()
        cur = state["current_user"]
        if not cur:
            show_login()
            return
        txt = ft.Text("Report Found Animal", size=18)
        species = ft.TextField(label="Species (optional)")
        location = ft.TextField(label="Location found")
        date = ft.TextField(label="Date (optional)")
        desc = ft.TextField(label="Description")
        msg = ft.Text("")

        def do_register_found(ev):
            with session_scope() as s:
                fr = FoundReport(
                    species=species.value.strip() or None,
                    found_location=location.value.strip() or None,
                    found_date=date.value.strip() or None,
                    found_description=desc.value.strip() or None,
                    finder_id=cur["id"]
                )
                s.add(fr)
            msg.value = "Found report saved."
            page.update()

        btn_back = ft.TextButton("Back", on_click=show_home)
        btn_save = ft.ElevatedButton("Save found report", on_click=do_register_found)
        page.add(txt, species, location, date, desc, ft.Row([btn_save, btn_back]), msg)

    # start on login
    show_login()

if __name__ == "__main__":
    ft.app(target=main)