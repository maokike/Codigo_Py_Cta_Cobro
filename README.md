# Generador de Cuentas de Cobro - Aplicación Web

Esta es una aplicación web Flask que automatiza la generación de cuentas de cobro en formato PDF a partir de un informe consolidado, también en PDF.

## Descripción

La aplicación permite a un usuario autenticado subir un informe en PDF. El sistema extrae la información de cada persona (nombre, cédula, montos), calcula los valores correspondientes a impuestos (ICA) y genera cuentas de cobro individuales. Finalmente, unifica todos los PDFs individuales en un único archivo consolidado que el usuario puede descargar.

El sistema utiliza carpetas de sesión para garantizar que los archivos de los usuarios no se mezclen y se limpian automáticamente al cerrar la sesión.

## Requisitos

- Python 3.6+
- Flask

## Instalación

1.  **Clonar el repositorio:**
    ```bash
    git clone <url_del_repositorio>
    cd <nombre_del_repositorio>
    ```

2.  **(Recomendado) Crear y activar un entorno virtual:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # En Windows: venv\\Scripts\\activate
    ```

3.  **Instalar las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

## Uso

1.  **Ejecutar la aplicación Flask:**
    ```bash
    flask run
    ```
    O alternativamente:
    ```bash
    python -m flask run
    ```

2.  **Acceder a la aplicación:**
    Abre tu navegador y ve a `http://127.0.0.1:5000`.

3.  **Iniciar sesión:**
    Utiliza las siguientes credenciales:
    -   **Usuario:** `kimirios@gmail.com`
    -   **Contraseña:** `KimoKeren2-*`

4.  **Generar cuentas de cobro:**
    -   Sube el archivo PDF del informe consolidado.
    -   Descarga los archivos PDF individuales o el consolidado desde el dashboard.

## Estructura de Archivos

```
mi_app/
├── app.py              # Lógica principal de Flask
├── templates/
│   ├── base.html       # Plantilla base
│   ├── login.html      # Página de inicio de sesión
│   └── dashboard.html  # Panel de control principal
├── static/
│   ├── style.css       # Estilos personalizados
│   └── script.js       # Lógica de frontend
├── requirements.txt      # Dependencias de Python
├── uploads/              # Archivos subidos temporalmente
├── cuentas_cobro_pdfs/   # PDFs consolidados generados
└── pdfs_individuales/    # PDFs individuales por sesión
```
