import flet as ft
from models import LostAnimal
from models import session

def main(page: ft.Page):
    page.title = "SIARA"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.window_width = 800
    page.window_height = 600
    page.window_resizable = True
    page.padding = 20

    lista_animais = ft.ListView()

    def registrar(e):
        try :
            nome_animal = animal.value
            local_perda = lost_location.value
            descricao = desc_animal.value
            contato = contact.value

            novo_animal = LostAnimal(name=nome_animal, lost_location=local_perda, desc_animal=descricao, contatct=contato)
            session.add(novo_animal)
            session.commit()

            lista_animais.controls.append(
                ft.Container(
                    ft.ListTile(
                        title=ft.Text(novo_animal.name),
                        subtitle=ft.Text(f"Perdido em: {novo_animal.lost_location}\nDescrição: {novo_animal.desc_animal}"),
                    ),
                    bgcolor=ft.Colors.BLACK12,
                    padding=15,
                    alignment=ft.alignment.center,
                    margin=3,
                    border_radius=10
                )
            )
            txt_acerto.visible = True
            txt_erro.visible = False
        except :
            txt_erro.visible = True
            txt_acerto.visible = False

        page.update()

    txt_erro = ft.Container(ft.Text('Erro ao registrar o animal!'), visible=False, bgcolor=ft.Colors.RED, padding=10, alignment=ft.alignment.center)
    txt_acerto = ft.Container(ft.Text('Animal registrado com sucesso!'), visible=False, bgcolor=ft.Colors.GREEN, padding=10, alignment=ft.alignment.center)

    txt_animal = ft.Text("Nome do Animal")
    animal = ft.TextField(label="Digite o nome do animal")
    txt_lost = ft.Text("Local em que o animal foi perdido")
    lost_location = ft.TextField(label="Digite o local")
    txt_desc_animal = ft.Text("Descreva o animal (opcional)")
    desc_animal = ft.TextField(label="Descrição")
    txt_contact = ft.Text("Contato para retorno")
    contact = ft.TextField(label="Digite o contato (telefone ou email)")
    btn_animal = ft.ElevatedButton("Registrar Animal Perdido", on_click=registrar, width=200)

    page.add(
        txt_animal,
        animal,
        txt_lost,
        lost_location,
        txt_desc_animal,
        desc_animal,
        txt_contact,
        contact,
        btn_animal
    )

    for a in session.query(LostAnimal).all():
        lista_animais.controls.append(
            ft.Container(
                ft.ListTile(
                    title=ft.Text(a.name),
                    subtitle=ft.Text(f"Perdido em: {a.lost_location}\nDescrição: {a.desc_animal}"),
                ),
                bgcolor=ft.Colors.BLACK12,
                padding=15,
                alignment=ft.alignment.center,
                margin=3,
                border_radius=10
            )
        )

    page.add(lista_animais)



if __name__ == "__main__":
    ft.app(target=main)