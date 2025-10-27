import os
import re
import pdfplumber
from datetime import datetime  # ← AÑADE ESTA IMPORTACIÓN
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from PyPDF2 import PdfMerger

# ==========================
#   EXTRAER DATOS DEL PDF
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
        
        # Calcular ICA (MODIFICADO: usar total para el cálculo)
        tarifa_ica = 6.9 if es_optometra else 9.66
        valor_ica = total * (tarifa_ica / 1000)  # Calcular ICA sobre el total
        
        # Calcular subtotal (MODIFICADO: subtotal = total + valor_ica)
        subtotal = total + valor_ica

        persona = {
            "nombre": nombre,
            "cedula": cedula,
            "subtotal": subtotal,  # Ahora subtotal incluye el ICA
            "total": total,        # Total permanece igual (neto a pagar)
            "es_optometra": es_optometra,
            "tarifa_ica": tarifa_ica,
            "valor_ica": valor_ica
        }
        
        personas.append(persona)
        print(f"✅ {nombre} - CC: {cedula} - Subtotal: {subtotal:,.0f} - Total: {total:,.0f} - Optómetra: {es_optometra} - ICA: {valor_ica:,.0f}")

    return personas

# ==========================
#   CONVERTIR NÚMERO A LETRAS
# ==========================

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

# ==========================
#   OBTENER FECHA ACTUAL EN ESPAÑOL
# ==========================

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

# ==========================
#   GENERAR PDF INDIVIDUAL (FORMATO EXACTO)
# ==========================

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
    fecha_actual = obtener_fecha_actual()  # ← FECHA ACTUAL
    c.drawString(margin_left, current_y, fecha_actual)
    current_y -= 25

    # Información de la empresa
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left, current_y, "GRUPO ÓPTICO ANDES S.A.S.")
    current_y -= 15
    c.setFont("Helvetica", 11)
    c.drawString(margin_left, current_y, "NIT: 901.308.210")
    current_y -= 25

    # "DEBE A"
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left, current_y, "DEBE A")
    current_y -= 25

    # Información personal
    c.drawString(margin_left, current_y, f"NOMBRE: {persona['nombre']}")
    current_y -= 20
    c.drawString(margin_left, current_y, f"C.C. No. {persona['cedula']}")
    current_y -= 30

    # Valores numéricos (MODIFICADO: subtotal = total + ICA)
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

    # Tabla de opciones (MODIFICADO: con valores centrados sobre líneas)
    opciones = [
        ("Responsable de IVA", "SÍ", "NO", False, None, None),
        ("Inscrito en el registro Nal de Vendedores", "SÍ", "NO", False, None, None),
        ("Código actividad económica en el Distrito Capital", "", "", True, "", ""),
        ("Tarifa de Retención de ICA asumido", "", "", True, f"{persona['tarifa_ica']}", f"{persona['valor_ica']:,.0f}"),
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
    current_y -= 120  # Baja la firma
    firma_x = margin_left
    c.line(firma_x, current_y, firma_x + 150, current_y)  # Línea de firma
    current_y -= 15
    c.drawString(firma_x, current_y, persona['nombre'])
    current_y -= 15
    c.drawString(firma_x, current_y, f"C.C. {persona['cedula']}")

    c.showPage()
    c.save()

# ==========================
#   UNIR TODOS LOS PDFS
# ==========================

def unir_pdfs(pdfs, output_path):
    merger = PdfMerger()
    for pdf in pdfs:
        merger.append(pdf)
    merger.write(output_path)
    merger.close()

# ==========================
#   MAIN
# ==========================

if __name__ == "__main__":
    pdf_informe = "INFORME CTAS COBRO HASTA 13 OCTUBRE GOA.pdf"
    output_dir = "cuentas_cobro_pdfs"
    os.makedirs(output_dir, exist_ok=True)

    print("🚀 Iniciando generación de cuentas de cobro...\n")
    print(f"📅 Fecha actual: {obtener_fecha_actual()}\n")  # Muestra la fecha actual
    
    personas = extraer_datos(pdf_informe)

    if not personas:
        print("❌ No se encontraron personas en el PDF. Verifica la estructura del documento.")
    else:
        print(f"\n🧾 Generando {len(personas)} cuentas de cobro personalizadas...\n")
        pdfs = []

        for persona in personas:
            # Crear nombre de archivo seguro
            nombre_archivo = re.sub(r'[^\w\s-]', '', persona['nombre'])
            nombre_archivo = re.sub(r'[-\s]+', '_', nombre_archivo).strip('-_')
            pdf_path = os.path.join(output_dir, f"{nombre_archivo}.pdf")
            
            generar_pdf(persona, pdf_path)
            pdfs.append(pdf_path)
            print(f"✅ Generado: {nombre_archivo}.pdf")

        print("\n📚 Unificando todos los PDF generados...")
        unir_pdfs(pdfs, "Cuentas_Cobro_Consolidadas.pdf")
        print("✅ Archivo final creado: Cuentas_Cobro_Consolidadas.pdf")
        print(f"🎉 Proceso completado. Se generaron {len(personas)} cuentas de cobro.")