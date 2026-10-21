"""
Enviar correos de cierre de mentorías InspiraSTEM 2026
=====================================================

Este archivo es un programa de Python. Al ejecutarlo, lee una hoja de
Google Sheets y envía un correo a cada persona que tenga email.

No hace falta entender todo el código para usarlo. Solo hay que
completar los datos de abajo y correr el programa una vez.


Qué necesitas antes
-------------------
1. Python instalado (versión 3.9 o más nueva).
   Compruébalo abriendo una terminal y escribiendo:

       python --version

   Si dice "no se reconoce" o "command not found", prueba:

       python3 --version

   Si tampoco funciona, instala Python desde https://www.python.org/downloads/
   En Windows, marca la casilla "Add python.exe to PATH" durante la instalación.

2. La librería pandas (sirve para leer la hoja como una tabla).
   En la misma terminal:

       python -m pip install pandas

   Si el comando que te funcionó fue python3, usa python3 en lugar de python.


Qué debes cambiar en este archivo (busca estas variables más abajo)
-------------------------------------------------------------------
- sheet_url
    Pega el enlace de la Google Sheet. La hoja tiene que poder verse
    con el enlace (Compartir > Cualquier persona con el enlace > Lector).
    La pestaña debe llamarse exactamente como sheet_name (ahora: bodega).
    Columnas obligatorias, con estos nombres:
        Email, Nombre, Carrera, Institucion

- EMAIL_ADDRESS
    El Gmail desde el que se envían los correos. Ejemplo: cuenta@gmail.com

- EMAIL_PASSWORD
    No es la contraseña normal de Gmail. Es una "contraseña de aplicación"
    de 16 letras, en 4 grupos. Se crea así:
        Cuenta de Google > Seguridad > Verificación en dos pasos
        > Contraseñas de aplicaciones > Crear
    Cópiala con los espacios, así: "abcd efgh ijkl mnop"

- copy1 y copy2
    Dos correos que reciben copia (Cc) de cada mensaje enviado.


Cómo ejecutarlo
---------------
1. Guarda este archivo después de poner tus datos.
2. Abre una terminal en la carpeta donde está el archivo.
   En Windows: en el Explorador, clic en la barra de dirección, escribe
   cmd y presiona Enter.
   En Mac: clic derecho en la carpeta > Nuevo terminal en la carpeta.
3. Escribe este comando y presiona Enter:

       python enviar_emails_python_para_fer.py

   Si python no funciona, prueba:

       python3 enviar_emails_python_para_fer.py

4. En la terminal verás una línea por cada persona:
       Sending to ...     (lo está enviando)
       Sent to ...        (ya se envió)
   Entre un correo y el siguiente espera 2 segundos, a propósito,
   para no saturar a Gmail.


Importante
----------
- En cuanto lo ejecutas, los correos salen de verdad. No hay botón
  de "deshacer". Conviene probar primero con una hoja de 1 sola fila
  (tu propio email) y, si llega bien, usar la hoja completa.
- Si Gmail responde "Username and Password not accepted", la contraseña
  de aplicación está mal o la verificación en dos pasos no está activa.
- Si dice "No module named pandas", falta el paso: python -m pip install pandas
- No compartas este archivo después de poner la contraseña de aplicación.
"""

from email.message import EmailMessage
from string import Template
import smtplib, time, os
import pandas as pd

# Nombre de la pestaña dentro del Google Sheet.
sheet_name = "bodega"
# Enlace completo de la hoja. Sustituye el de ejemplo por el enlace real.
sheet_url = "https://docs.google.com/spreadsheets/d/kdjvndkjnfldjflsknlvnlvkmlkdmdc/edit?usp=sharing"

# Extract the sheet ID and build a CSV export URL
sheet_id = sheet_url.split("/d/")[1].split("/")[0]
csv_url = (
    f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
    f"?tqx=out:csv&sheet={sheet_name}"
)

# Read into a DataFrame
df = pd.read_csv(csv_url)
recipients = [
    {
        "email": row["Email"],
        "name": "" if pd.isna(row["Nombre"]) else row["Nombre"],
        "position": "" if pd.isna(row["Carrera"]) else row["Carrera"],
        "afiliacion": "" if pd.isna(row["Institucion"]) else row["Institucion"],
    }
    for _, row in df.dropna(subset=["Email"]).iterrows()
    if str(row["Email"]).strip()
]

# --- Subject ---
subject = 'Mentorías InspiraSTEM 2026: cierre de mentorías y registro de reuniones [Acción requerida]'

# --- Email body template (usa $placeholders, no llaves {}) ---
email_template = Template(r'''
<html>
  <body>
    <p>Saludos cordiales,</p>

    $header_block

    <p>Esperamos que estés teniendo una bonita semana.</p>

    <p>
      Te escribimos para recordarte que se aproxima el cierre del
      <b>programa de mentorías InspiraSTEM 2026</b>.
      Si aún no has realizado una segunda reunión con tus mentees,
      recuerda que tienes hasta el <b>23 de octubre de 2026</b> para hacerlo.
    </p>

    <p>
      También queremos llevar un registro de las reuniones realizadas.
      Recuerda que es necesario completar un <b>mínimo de dos reuniones</b>
      con tus mentees para recibir el certificado de participación como mentor.
    </p>

    <p>
      <b>Por favor, completa el siguiente formulario con las fechas de tus reuniones:</b><br>
      <a href="https://forms.gle/zLxBg2WwMgKRZ7VN8"
         target="_blank" rel="noopener noreferrer">
        Registrar mis reuniones de mentoría
      </a>
    </p>

    <p>
      Te recordamos que las sesiones deben realizarse <b>exclusivamente en línea</b>,
      a través de plataformas virtuales como Zoom, Teams u otras similares.
      <b>Las reuniones presenciales están estrictamente prohibidas.</b>
    </p>

    <p>
      Por favor, revisa también el documento
      <a href="https://drive.google.com/file/d/1Bo5z1TJRs-B7iQlhecSqCaBz3t2ERulM/view?usp=sharing"
         target="_blank" rel="noopener noreferrer">
        Términos de Participación y Código de Conducta — Mentorías InspiraSTEM
      </a>.
      Recuerda mantener la comunicación en un ámbito estrictamente profesional
      y evitar solicitar datos personales que no correspondan al programa.
    </p>

    <p>
      El equipo de InspiraSTEM está muy agradecido por tu tiempo, compromiso
      y apoyo. También queremos agradecer a quienes nos enviaron fotos
      de sus sesiones de mentoría.
      <b>¡Qué bonito es ver crecer a El Salvador en las ciencias!</b>
    </p>

    <p>
      Saludos cordiales,<br>
      <b>Equipo de Mentorías InspiraSTEM</b>
    </p>
  </body>
</html>
''')

# --- Helper to build the conditional header block ---
def build_header_block(rec):
    parts = [
      (rec.get('name') or '').strip(),
      (rec.get('position') or '').strip(),
      (rec.get('afiliacion') or '').strip(),
    ]
    parts = [p for p in parts if p]  # keep only non-empty
    if not parts:
      return ''  # no block at all (so no extra blank paragraph)
    # join with <br> so it’s a single neat paragraph, all in italics
    joined = '<br>\n      '.join(parts)
    return f'''
    <p>
      <em>{joined}</em>
    </p>'''

# --- Datos de envío: cámbialos antes de ejecutar el programa ---
# Gmail que envía los correos.
EMAIL_ADDRESS = 'tuemail@gmail.com'
# Contraseña de aplicación (16 letras). No uses la contraseña normal de Gmail.
EMAIL_PASSWORD = 'sjkd shdj okms sjoo'  # App Password

# Estas dos personas reciben una copia de cada correo.
copy1 = 'emailcopia1@gmail.com'
copy2 = 'emailcopia2@gmail.com'

# Recorre la lista de personas y envía un correo a cada una.
# Este ciclo empieza solo: no hay que llamarlo. Al ejecutar el archivo, llega aquí.
for rec in recipients:
    
    # filelettername = "inspirastem2025.pdf"
    # print(f"Checking file: {filelettername}")
    # if not os.path.exists(filelettername):
    #     print(f"File {filelettername} not found for {rec.get('name','')}  {rec['email']}")
    #     continue

    print(f"Sending to {rec.get('name','(sin nombre)')} at {rec['email']}")

    header_block = build_header_block(rec)

    EMAIL_CONTENT = email_template.substitute(
        header_block=header_block
    )

    # --- Create email ---
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = rec['email']
    msg['Cc'] = ', '.join([copy1, copy2])
    msg.add_alternative(EMAIL_CONTENT, subtype='html')

    # --- Send email via SMTP ---
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as smtp:
        smtp.set_debuglevel(0)
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

    print(f"Sent to {rec.get('name','(sin nombre)')} at {rec['email']}")
    time.sleep(2.0)