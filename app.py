import os
import re
import shutil
from datetime import datetime
from functools import wraps

import pdfplumber
from PyPDF2 import PdfMerger
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, send_file

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-change-me'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['INDIVIDUAL_PDFS_FOLDER'] = 'pdfs_individuales'
app.config['CONSOLIDATED_PDFS_FOLDER'] = 'cuentas_cobro_pdfs'

# Ensure all necessary folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['INDIVIDUAL_PDFS_FOLDER'], exist_ok=True)
os.makedirs(app.config['CONSOLIDATED_PDFS_FOLDER'], exist_ok=True)

# ==========================
#   PDF PROCESSING LOGIC (MEJORADO)
# ==========================

def extraer_datos(pdf_path):
    print("📖 Extrayendo texto del PDF con pdfplumber...")
    texto = ""

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            texto += page.extract_text() + "\n"
            print(f"✅ Página {i}/{len(pdf.pages)} leída")

    # Patrón mejorado para extraer personas
    patron_persona = r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]+)\s*\n\s*Identificaci[oó]n:\s*(\d{6,12})[\s\S]*?Total para Cuentas por Cobrar[\s\S]*?([\d\.,]+)\s*\n\s*Total:\s*([\d\.,]+)"

    personas_encontradas = re.findall(patron_persona, texto)
    personas = []

    print(f"\n🔍 Se encontraron {len(personas_encontradas)} personas en el informe.\n")

    for nombre, cedula, subtotal_str, total_str in personas_encontradas:
        nombre = nombre.strip()
        cedula = cedula.strip()

        # Limpiar y convertir valores numéricos
        total = float(total_str.replace(".", "").replace(",", "."))  # Este es el valor neto a pagar

        # Buscar si es optómetra en el bloque correspondiente
        bloque_patron = rf"{re.escape(nombre)}\s*\n\s*Identificaci[oó]n:\s*{re.escape(cedula)}[\s\S]*?Total para Cuentas por Cobrar"
        bloque_match = re.search(bloque_patron, texto)

        es_optometra = False
        if bloque_match:
            bloque_texto = bloque_match.group(0)
            es_optometra = "OPTOMETRA" in bloque_texto.upper()

        # NUEVA LÓGICA: Solo aplicar ICA si el total supera $100.000
        if total > 100000:
            # Calcular ICA (MODIFICADO: usar total para el cálculo)
            tarifa_ica = 6.9 if es_optometra else 9.66
            valor_ica = total * (tarifa_ica / 1000)  # Calcular ICA sobre el total

            # Calcular subtotal (MODIFICADO: subtotal = total + valor_ica)
            subtotal = total + valor_ica
            
            print(f"✅ {nombre} - CC: {cedula} - Subtotal: {subtotal:,.0f} - Total: {total:,.0f} - Optómetra: {es_optometra} - ICA APLICADO: {valor_ica:,.0f}")
        else:
            # Si el total es menor o igual a $100.000, no se aplica ICA
            tarifa_ica = 0
            valor_ica = 0
            subtotal = total  # Subtotal igual al total
            
            print(f"✅ {nombre} - CC: {cedula} - Subtotal: {subtotal:,.0f} - Total: {total:,.0f} - Optómetra: {es_optometra} - SIN RETENCIÓN ICA")

        persona = {
            "nombre": nombre,
            "cedula": cedula,
            "subtotal": subtotal,
            "total": total,
            "es_optometra": es_optometra,
            "tarifa_ica": tarifa_ica,
            "valor_ica": valor_ica,
            "aplica_retencion": total > 100000  # Nuevo campo para indicar si aplica retención
        }

        personas.append(persona)

    return personas

def numero_a_letras(numero):
    """Convierte un número a letras en español"""
    unidades = ['', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE']
    decenas = ['', 'DIEZ', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA']
    especiales = ['DIEZ', 'ONCE', 'DOCE', 'TRECE', 'CATORCE', 'QUINCE', 'DIECISÉIS', 'DIECISIETE', 'DIECIOCHO', 'DIECINUEVE']

    entero = int(numero)

    if entero == 0:
        return "CERO"
    elif entero < 10:
        return unidades[entero]
    elif entero < 20:
        return especiales[entero - 10]
    elif entero < 100:
        decena = entero // 10
        unidad = entero % 10
        if unidad == 0:
            return decenas[decena]
        else:
            return f"{decenas[decena]} Y {unidades[unidad]}"
    elif entero < 1000:
        centena = entero // 100
        resto = entero % 100
        if centena == 1:
            if resto == 0:
                return "CIEN"
            else:
                return f"CIENTO {numero_a_letras(resto)}"
        else:
            centena_str = unidades[centena]
            if centena == 5:
                centena_str = "QUINIENTOS"
            elif centena == 7:
                centena_str = "SETECIENTOS"
            elif centena == 9:
                centena_str = "NOVECIENTOS"
            elif centena > 1:
                centena_str = unidades[centena] + "CIENTOS"

            if resto == 0:
                return centena_str
            else:
                return f"{centena_str} {numero_a_letras(resto)}"
    elif entero < 1000000:
        miles = entero // 1000
        resto = entero % 1000
        if miles == 1:
            miles_str = "MIL"
        else:
            miles_str = f"{numero_a_letras(miles)} MIL"

        if resto == 0:
            return miles_str
        else:
            return f"{miles_str} {numero_a_letras(resto)}"
    else:
        return "NÚMERO DEMASIADO GRANDE"

def obtener_fecha_actual():
    """Obtiene la fecha actual en formato: 'BOGOTÁ, 27 DE OCTUBRE DE 2024'"""
    meses = [
        'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
        'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'
    ]

    ahora = datetime.now()
    dia = ahora.day
    mes = meses[ahora.month - 1]
    año = ahora.year

    return f"BOGOTÁ, {dia} DE {mes} DE {año}"

def generar_pdf(persona, output_path):
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    # Configuración inicial
    margin_left = 40
    margin_right = width - 40
    current_y = height - 40

    # Título principal
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width/2, current_y, "CUENTA DE COBRO")
    current_y -= 30

    # Fecha y lugar (MODIFICADO: fecha dinámica)
    c.setFont("Helvetica", 11)
    fecha_actual = obtener_fecha_actual()
    c.drawString(margin_left, current_y, fecha_actual)
    current_y -= 25

    # Información de la empresa
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left, current_y, "GRUPO ÓPTICO ANDES S.A.S.")
    current_y -= 15
    c.setFont("Helvetica", 11)
    c.drawString(margin_left, current_y, "NIT: 901.308.210")
    current_y -= 25

    # 4 ESPACIOS ANTES DE "DEBE A"
    current_y -= 60  # 4 líneas * 15 puntos cada una ≈ 60 puntos

    # "DEBE A"
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left, current_y, "DEBE A")
    current_y -= 25

    # 4 ESPACIOS DESPUÉS DE "DEBE A"
    current_y -= 60  # 4 líneas * 15 puntos cada una ≈ 60 puntos

    # Información personal
    c.drawString(margin_left, current_y, f"NOMBRE: {persona['nombre']}")
    current_y -= 20
    c.drawString(margin_left, current_y, f"C.C. No. {persona['cedula']}")
    current_y -= 30

    # 4 ESPACIOS DESPUÉS DE "C.C. No. 1023880041"
    current_y -= 60  # 4 líneas * 15 puntos cada una ≈ 60 puntos

    # Valores numéricos (MODIFICADO: lógica condicional para ICA)
    c.drawString(margin_left, current_y, f"Valor subtotal: {persona['subtotal']:,.0f}")
    current_y -= 20
    c.drawString(margin_left, current_y, f"Valor total: {persona['total']:,.0f}")
    current_y -= 20

    # Valor en letras
    valor_letras = numero_a_letras(int(persona['total']))
    c.drawString(margin_left, current_y, f"Valor en letras: {valor_letras} PESOS M.L.")
    current_y -= 25

    # Concepto
    c.drawString(margin_left, current_y, "Por concepto de: TURNOS Y METAS")
    current_y -= 30

    # Texto legal
    c.setFont("Helvetica", 10)
    texto_legal = "De acuerdo a ley 1819 de 2016 informo que no tengo trabajadores a mi cargo y solicito la aplicación del art. 383 et."
    # Dividir texto si es muy largo
    if len(texto_legal) > 80:
        palabras = texto_legal.split()
        linea1 = ' '.join(palabras[:len(palabras)//2])
        linea2 = ' '.join(palabras[len(palabras)//2:])
        c.drawString(margin_left, current_y, linea1)
        current_y -= 15
        c.drawString(margin_left, current_y, linea2)
        current_y -= 25
    else:
        c.drawString(margin_left, current_y, texto_legal)
        current_y -= 30

    # Tabla de opciones (MODIFICADO: manejar casos con y sin retención)
    # Si no aplica retención, mostrar campos vacíos para ICA
    if persona['aplica_retencion']:
        valor_ica_str = f"{persona['valor_ica']:,.0f}"
        tarifa_ica_str = f"{persona['tarifa_ica']}"
    else:
        valor_ica_str = ""
        tarifa_ica_str = ""

    opciones = [
        ("Responsable de IVA", "SÍ", "NO", False, None, None),
        ("Inscrito en el registro Nal de Vendedores", "SÍ", "NO", False, None, None),
        ("Código actividad económica en el Distrito Capital", "", "", True, "", ""),
        ("Tarifa de Retención de ICA asumido", "", "", True, tarifa_ica_str, valor_ica_str),
        ("Tarifa de Retención en la Fuente", "", "", True, "", "")
    ]

    # Posiciones fijas para las columnas
    col1_x = margin_left
    col2_x = margin_right - 120  # Columna SÍ/NO
    col3_x = margin_right - 60   # Columna NO
    valor_line_x = margin_right - 100  # Posición para las líneas de VALOR

    for opcion, col2, col3, tiene_lineas, valor_antes, valor_despues in opciones:
        c.setFont("Helvetica", 10)
        c.drawString(col1_x, current_y, opcion)

        if tiene_lineas:
            # Línea antes de VALOR
            linea_antes_x1 = valor_line_x - 45
            linea_antes_x2 = valor_line_x - 5
            c.line(linea_antes_x1, current_y - 2, linea_antes_x2, current_y - 2)

            # Valor antes (centrado sobre la línea)
            if valor_antes:
                texto_width = c.stringWidth(valor_antes, "Helvetica", 10)
                texto_x = linea_antes_x1 + (linea_antes_x2 - linea_antes_x1 - texto_width) / 2
                c.drawString(texto_x, current_y, valor_antes)

            # VALOR
            c.drawString(valor_line_x, current_y, "VALOR")
            valor_width = c.stringWidth("VALOR", "Helvetica", 10)

            # Línea después de VALOR
            linea_despues_x1 = valor_line_x + valor_width + 5
            linea_despues_x2 = valor_line_x + valor_width + 45
            c.line(linea_despues_x1, current_y - 2, linea_despues_x2, current_y - 2)

            # Valor después (centrado sobre la línea)
            if valor_despues:
                texto_width = c.stringWidth(valor_despues, "Helvetica", 10)
                texto_x = linea_despues_x1 + (linea_despues_x2 - linea_despues_x1 - texto_width) / 2
                c.drawString(texto_x, current_y, valor_despues)
        else:
            # Para las opciones SÍ/NO normales
            if col2:
                c.drawString(col2_x, current_y, col2)
            if col3:
                c.drawString(col3_x, current_y, col3)
                # Agregar "X" en negrita después del NO
                c.setFont("Helvetica-Bold", 12)
                c.drawString(col3_x + 20, current_y, "X")
                c.setFont("Helvetica", 10)

        current_y -= 20

    current_y -= 30

    # FIRMA (alineada a la IZQUIERDA - más abajo)
    current_y -= 80  # Baja la firma
    firma_x = margin_left
    c.line(firma_x, current_y, firma_x + 150, current_y)  # Línea de firma
    current_y -= 15
    c.drawString(firma_x, current_y, persona['nombre'])
    current_y -= 15
    c.drawString(firma_x, current_y, f"C.C. {persona['cedula']}")

    c.showPage()
    c.save()

def unir_pdfs(pdfs, output_path):
    merger = PdfMerger()
    for pdf in pdfs:
        merger.append(pdf)
    merger.write(output_path)
    merger.close()

# ==========================
#   AUTHENTICATION
# ==========================

# Hardcoded user credentials
USER_EMAIL = "kimirios@gmail.com"
USER_PASSWORD_HASH = generate_password_hash("KimoKeren2-*")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Por favor, inicia sesión para acceder a esta página.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if email == USER_EMAIL and check_password_hash(USER_PASSWORD_HASH, password):
            session['user_id'] = email
            session['session_id'] = os.urandom(16).hex() # Unique ID for this session
            flash("Inicio de sesión exitoso.", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Credenciales incorrectas. Inténtalo de nuevo.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    # Clean up all session-related files before logging out
    session_id = session.get('session_id')
    if session_id:
        # Remove individual PDFs folder
        individual_folder = os.path.join(app.config['INDIVIDUAL_PDFS_FOLDER'], session_id)
        if os.path.exists(individual_folder):
            shutil.rmtree(individual_folder)

        # Remove uploaded PDF folder
        upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        if os.path.exists(upload_folder):
            shutil.rmtree(upload_folder)

        # Remove consolidated PDF
        processed_data = session.get('processed_data')
        if processed_data and 'consolidated_file' in processed_data:
            consolidated_file = os.path.join(app.config['CONSOLIDATED_PDFS_FOLDER'], processed_data['consolidated_file'])
            if os.path.exists(consolidated_file):
                os.remove(consolidated_file)

    session.clear()
    flash("Has cerrado la sesión y todos los archivos temporales han sido eliminados.", "info")
    return redirect(url_for('login'))

@app.route('/clear_session')
@login_required
def clear_session_files():
    session_id = session.get('session_id')
    if session_id:
        # Clean up logic is the same as logout
        individual_folder = os.path.join(app.config['INDIVIDUAL_PDFS_FOLDER'], session_id)
        if os.path.exists(individual_folder):
            shutil.rmtree(individual_folder)

        upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        if os.path.exists(upload_folder):
            shutil.rmtree(upload_folder)

        processed_data = session.get('processed_data')
        if processed_data and 'consolidated_file' in processed_data:
            consolidated_file = os.path.join(app.config['CONSOLIDATED_PDFS_FOLDER'], processed_data['consolidated_file'])
            if os.path.exists(consolidated_file):
                os.remove(consolidated_file)

        session.pop('processed_data', None) # Remove data from session
        flash("Todos los archivos de la sesión actual han sido eliminados.", "success")
    return redirect(url_for('dashboard'))

# ==========================
#   CORE APP ROUTES
# ==========================

@app.route('/')
@login_required
def dashboard():
    processed_data = session.get('processed_data', None)
    return render_template('dashboard.html', processed_data=processed_data)

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'pdf_file' not in request.files:
        flash('No se encontró el archivo.', 'danger')
        return redirect(url_for('dashboard'))

    file = request.files['pdf_file']
    if file.filename == '':
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('dashboard'))

    if file and file.filename.endswith('.pdf'):
        filename = secure_filename(file.filename)

        # Create a unique session folder for uploads
        session_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], session['session_id'])
        os.makedirs(session_upload_folder, exist_ok=True)
        save_path = os.path.join(session_upload_folder, filename)
        file.save(save_path)

        try:
            personas = extraer_datos(save_path)
            if not personas:
                flash("No se encontraron datos de personas en el PDF. Revisa el formato.", "warning")
                return redirect(url_for('dashboard'))

            # Create session folder for individual PDFs
            session_individual_folder = os.path.join(app.config['INDIVIDUAL_PDFS_FOLDER'], session['session_id'])
            os.makedirs(session_individual_folder, exist_ok=True)

            individual_pdfs = []
            for persona in personas:
                # Crear nombre de archivo seguro
                nombre_archivo = re.sub(r'[^\w\s-]', '', persona['nombre'])
                nombre_archivo = re.sub(r'[-\s]+', '_', nombre_archivo).strip('-_') + '.pdf'
                pdf_path = os.path.join(session_individual_folder, nombre_archivo)

                generar_pdf(persona, pdf_path)
                individual_pdfs.append({
                    "nombre": persona['nombre'],
                    "cedula": persona['cedula'],
                    "filename": nombre_archivo
                })

            # Create consolidated PDF
            consolidated_filename = f"Cuentas_Cobro_Consolidadas_{session['session_id']}.pdf"
            consolidated_path = os.path.join(app.config['CONSOLIDATED_PDFS_FOLDER'], consolidated_filename)

            # Unir todos los PDFs individuales
            pdf_paths = [os.path.join(session_individual_folder, p['filename']) for p in individual_pdfs]
            unir_pdfs(pdf_paths, consolidated_path)

            session['processed_data'] = {
                "individual_files": individual_pdfs,
                "consolidated_file": consolidated_filename,
                "total_personas": len(individual_pdfs)
            }

            flash(f"¡Se generaron {len(individual_pdfs)} cuentas de cobro con éxito!", "success")

        except Exception as e:
            flash(f"Ocurrió un error al procesar el PDF: {str(e)}", "danger")

        return redirect(url_for('dashboard'))
    else:
        flash('Tipo de archivo no válido. Por favor, sube un PDF.', 'warning')
        return redirect(url_for('dashboard'))

# ==========================
#   FILE SERVING
# ==========================

@app.route('/downloads/individual/<filename>')
@login_required
def download_individual_file(filename):
    directory = os.path.join(app.config['INDIVIDUAL_PDFS_FOLDER'], session['session_id'])
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/view/individual/<filename>')
@login_required
def view_individual_file(filename):
    directory = os.path.join(app.config['INDIVIDUAL_PDFS_FOLDER'], session['session_id'])
    return send_from_directory(directory, filename, as_attachment=False)

@app.route('/downloads/consolidated')
@login_required
def download_consolidated_file():
    processed_data = session.get('processed_data')
    if not processed_data or 'consolidated_file' not in processed_data:
        flash("No hay archivo consolidado disponible.", "warning")
        return redirect(url_for('dashboard'))

    filename = processed_data['consolidated_file']
    directory = app.config['CONSOLIDATED_PDFS_FOLDER']
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/view/consolidated')
@login_required
def view_consolidated_file():
    processed_data = session.get('processed_data')
    if not processed_data or 'consolidated_file' not in processed_data:
        flash("No hay archivo consolidado disponible.", "warning")
        return redirect(url_for('dashboard'))

    filename = processed_data['consolidated_file']
    directory = app.config['CONSOLIDATED_PDFS_FOLDER']
    return send_from_directory(directory, filename, as_attachment=False)

if __name__ == '__main__':
    app.run(debug=True)
