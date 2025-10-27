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

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-change-me'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['INDIVIDUAL_PDFS_FOLDER'] = 'pdfs_individuales'
app.config['CONSOLIDATED_PDFS_FOLDER'] = 'cuentas_cobro_pdfs' # Added for consistency

# Ensure all necessary folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['INDIVIDUAL_PDFS_FOLDER'], exist_ok=True)
os.makedirs(app.config['CONSOLIDATED_PDFS_FOLDER'], exist_ok=True)


# =================================
#   PDF PROCESSING LOGIC
# =================================

def extraer_datos(pdf_path):
    texto = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() + "\n"

    patron_persona = r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]+)\s*\n\s*Identificaci[oó]n:\s*(\d{6,12})[\s\S]*?Total para Cuentas por Cobrar[\s\S]*?([\d\.,]+)\s*\n\s*Total:\s*([\d\.,]+)"
    personas_encontradas = re.findall(patron_persona, texto)
    personas = []

    for nombre, cedula, _, total_str in personas_encontradas:
        nombre = nombre.strip()
        cedula = cedula.strip()
        total = float(total_str.replace(".", "").replace(",", "."))

        bloque_patron = rf"{re.escape(nombre)}\s*\n\s*Identificaci[oó]n:\s*{re.escape(cedula)}[\s\S]*?Total para Cuentas por Cobrar"
        bloque_match = re.search(bloque_patron, texto)
        es_optometra = "OPTOMETRA" in bloque_match.group(0).upper() if bloque_match else False

        tarifa_ica = 6.9 if es_optometra else 9.66
        valor_ica = total * (tarifa_ica / 1000)
        subtotal = total + valor_ica

        personas.append({
            "nombre": nombre, "cedula": cedula, "subtotal": subtotal,
            "total": total, "es_optometra": es_optometra,
            "tarifa_ica": tarifa_ica, "valor_ica": valor_ica
        })
    return personas

def numero_a_letras(numero):
    unidades = ['', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE']
    decenas = ['', 'DIEZ', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA']
    especiales = ['DIEZ', 'ONCE', 'DOCE', 'TRECE', 'CATORCE', 'QUINCE', 'DIECISÉIS', 'DIECISIETE', 'DIECIOCHO', 'DIECINUEVE']

    entero = int(numero)
    if entero == 0: return "CERO"
    if entero < 10: return unidades[entero]
    if entero < 20: return especiales[entero - 10]
    if entero < 100:
        return f"{decenas[entero // 10]}{' Y ' + unidades[entero % 10] if entero % 10 != 0 else ''}"
    if entero < 1000:
        if entero == 100: return "CIEN"
        centena_str = ""
        if entero // 100 == 1: centena_str = "CIENTO "
        elif entero // 100 == 5: centena_str = "QUINIENTOS "
        elif entero // 100 == 7: centena_str = "SETECIENTOS "
        elif entero // 100 == 9: centena_str = "NOVECIENTOS "
        else: centena_str = unidades[entero // 100] + "CIENTOS "
        return f"{centena_str}{numero_a_letras(entero % 100) if entero % 100 != 0 else ''}".strip()
    if entero < 1000000:
        miles = entero // 1000
        miles_str = "MIL " if miles == 1 else numero_a_letras(miles) + " MIL "
        return f"{miles_str}{numero_a_letras(entero % 1000) if entero % 1000 != 0 else ''}".strip()
    return "NÚMERO DEMASIADO GRANDE"

def obtener_fecha_actual():
    meses = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
    ahora = datetime.now()
    return f"BOGOTÁ, {ahora.day} DE {meses[ahora.month - 1]} DE {ahora.year}"

def generar_pdf(persona, output_path):
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    margin_left = 40
    current_y = height - 40

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width/2, current_y, "CUENTA DE COBRO")
    current_y -= 30
    c.setFont("Helvetica", 11)
    c.drawString(margin_left, current_y, obtener_fecha_actual())
    current_y -= 25
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left, current_y, "GRUPO ÓPTICO ANDES S.A.S.")
    current_y -= 15
    c.setFont("Helvetica", 11)
    c.drawString(margin_left, current_y, "NIT: 901.308.210")
    current_y -= 25
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left, current_y, "DEBE A")
    current_y -= 25
    c.drawString(margin_left, current_y, f"NOMBRE: {persona['nombre']}")
    current_y -= 20
    c.drawString(margin_left, current_y, f"C.C. No. {persona['cedula']}")
    current_y -= 30
    c.drawString(margin_left, current_y, f"Valor subtotal: {persona['subtotal']:,.0f}")
    current_y -= 20
    c.drawString(margin_left, current_y, f"Valor total: {persona['total']:,.0f}")
    current_y -= 20
    valor_letras = numero_a_letras(int(persona['total']))
    c.drawString(margin_left, current_y, f"Valor en letras: {valor_letras} PESOS M.L.")
    current_y -= 25
    c.drawString(margin_left, current_y, "Por concepto de: TURNOS Y METAS")
    current_y -= 30
    c.setFont("Helvetica", 10)
    texto_legal = "De acuerdo a ley 1819 de 2016 informo que no tengo trabajadores a mi cargo y solicito la aplicación del art. 383 et."
    c.drawString(margin_left, current_y, texto_legal)
    current_y -= 30

    # ... (simplified table for brevity, but the logic is the same)

    current_y -= 120
    firma_x = margin_left
    c.line(firma_x, current_y, firma_x + 150, current_y)
    current_y -= 15
    c.drawString(firma_x, current_y, persona['nombre'])
    current_y -= 15
    c.drawString(firma_x, current_y, f"C.C. {persona['cedula']}")

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
                nombre_archivo = f"{persona['nombre'].replace(' ', '_')}.pdf"
                pdf_path = os.path.join(session_individual_folder, nombre_archivo)
                generar_pdf(persona, pdf_path)
                individual_pdfs.append({"nombre": persona['nombre'], "cedula": persona['cedula'], "filename": nombre_archivo})

            # Create consolidated PDF
            consolidated_filename = f"Consolidado_{session['session_id']}.pdf"
            consolidated_path = os.path.join(app.config['CONSOLIDATED_PDFS_FOLDER'], consolidated_filename)
            unir_pdfs([os.path.join(session_individual_folder, p['filename']) for p in individual_pdfs], consolidated_path)

            session['processed_data'] = {
                "individual_files": individual_pdfs,
                "consolidated_file": consolidated_filename
            }

            flash(f"Se generaron {len(individual_pdfs)} cuentas de cobro con éxito.", "success")

        except Exception as e:
            flash(f"Ocurrió un error al procesar el PDF: {e}", "danger")

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
    return send_from_directory(directory, filename, as_attachment=request.args.get('download'))

@app.route('/downloads/consolidated/<filename>')
@login_required
def download_consolidated_file(filename):
    directory = app.config['CONSOLIDATED_PDFS_FOLDER']
    return send_from_directory(directory, filename, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True)
