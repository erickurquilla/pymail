# pymail

Programa para enviar una carta a cada persona de una hoja de Google. Cada carta es una carpeta dentro de `campaigns/`. El programa no guarda el correo ni la contraseña de Gmail.

La campaña de ejemplo es `campaigns/example`.

## Qué necesitas

1. Python 3.11 o más nuevo. En una terminal:

       python3 --version

2. Una contraseña de aplicación de Gmail, no la contraseña normal de la cuenta.

   Cuenta de Google, Seguridad, Verificación en dos pasos, Contraseñas de aplicaciones, Crear.

   Cuando el programa la pida, escríbela en la terminal. Puede llevar espacios, así: `abcd efgh ijkl mnop`. No la guardes en un archivo. El correo de Gmail también se escribe en la terminal, y ese sí se muestra.

## Preparar el programa (una sola vez)

Abre una terminal en esta carpeta y escribe:

    python3 -m venv .venv
    .venv/bin/pip install -e .

En la hoja de Google, Compartir, Cualquier persona con el enlace, Lector. El nombre de la pestaña y las columnas están en `campaigns/example/campaign.toml`. En el ejemplo la pestaña se llama `Sheet1` y las columnas son `Email`, `Nombre`, `Carrera`, `Institucion`. `sheet_id` puede ser el enlace para editar o solo el id. La pestaña sigue en `sheet_name`.

## Ver la carta sin enviarla

    .venv/bin/pymail preview campaigns/example

Esto no manda ningún correo. Muestra cuántas personas hay, los correos repetidos, los que no parecen un email, las primeras cinco personas con su correo, nombre, carrera e institución, y una carta de muestra.

## Probar con un solo correo

Este comando manda una sola carta a la dirección que escribas, usando los datos de la primera fila de la hoja:

    .venv/bin/pymail send campaigns/example --limit 1 --to tu@gmail.com

Ese envío de prueba no copia las direcciones de `cc` y no se escribe en `sends.db`, así que puedes repetirlo y la lista real sigue pendiente. También se envía cuando toda la lista ya fue mandada. Revisa que haya llegado bien antes de mandar el resto.

Antes de mandar, el programa muestra el asunto, la dirección de prueba y el texto de la carta. En cada paso la pregunta muestra `[yes/no]`. Solo `yes` confirma. Cualquier otra respuesta, incluida `y`, cancela el envío y no manda nada. Si confirmas, pide el correo de Gmail y lo muestra. Después pide la contraseña de aplicación y no la muestra. Si no escribes el correo o la contraseña, también cancela.

## Enviar la lista

    .venv/bin/pymail send campaigns/example

Antes de mandar, el programa muestra el asunto, el destinatario y el texto del primer correo que todavía no está en el registro. En cada paso la pregunta muestra `[yes/no]` y solo `yes` confirma. Después pregunta si se envían todos los correos pendientes de la hoja, e indica cuántos son, y otra vez solo `yes` sigue. Si confirmas, pide el correo de Gmail y lo muestra. Después pide la contraseña de aplicación y no la muestra. Cualquier otra respuesta cancela el envío y no manda nada. Si no escribes el correo o la contraseña, también cancela.

Entre un correo y el siguiente el programa espera 2 segundos. Si se corta a la mitad, vuelve a ejecutar el mismo comando: no repite los que ya se enviaron. El registro queda en `sends.db` en esta carpeta. Ese archivo tampoco se sube a GitHub.

En la terminal, cada persona se ve así:

    Sending to Example at example@example.com
    Sent to Example at example@example.com

## Otra campaña

Copia la carpeta `campaigns/example`, cambia el `id`, el asunto, la hoja y la carta. `body_format` elige el archivo: `txt` lee `body.txt` y arma el HTML; `html` lee `body.html` y arma el texto. Si no está, vale `txt`. El correo lleva las dos versiones, y el programa de correo muestra la que sabe leer. El ejemplo usa `html`. `body.txt` es la misma carta; para enviarla, cambia `body_format` a `txt`.

Con `txt`, una línea en blanco empieza un párrafo, un salto de línea simple se vuelve un salto, y las direcciones web se vuelven enlaces. `$header_block` es el lugar del nombre, la carrera y la institución. Si los tres están vacíos, ese bloque no aparece. En `body.html` va entre bloques, porque el programa lo reemplaza por un párrafo en cursiva.

Para que otras personas reciban copia, pon el nombre de esa columna de la hoja en `cc_columns`. Cada fila copia solo las direcciones de su propia celda. Si no quieres copias, déjalo así: `cc_columns = []`.
