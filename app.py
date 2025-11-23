import flet as ft

def main(page: ft.Page):
    page.title = "SIARA"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.window_width = 800
    page.window_height = 600
    page.window_resizable = True
    page.padding = 20

    def registrar(e):
        nome_animal = animal.value
        local_perda = lost.value
        print(f"Animal Registrado: {nome_animal}, Local de Perda: {local_perda}")
        animal.value = ""
        lost.value = ""
        page.update()

    txt_animal = ft.Text("Nome do Animal", width=300)
    animal = ft.TextField(label="Digite o nome do animal", width=300)
    txt_lost = ft.Text("Local em que o animal foi perdido", width=300)
    lost = ft.TextField(label="Digite o local", width=300)
    btn_animal = ft.ElevatedButton("Registrar Animal Perdido", on_click=registrar, width=200)

    page.add(
        txt_animal,
        animal,
        txt_lost,
        lost,
        btn_animal
    )



if __name__ == "__main__":
    ft.app(target=main)