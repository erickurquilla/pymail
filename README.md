# pymail

Programa para enviar una carta a cada persona de una hoja de Google. Cada carta es una carpeta dentro de `campaigns/`. El programa no guarda la contraseña de Gmail.

La primera campaña es el cierre de mentorías InspiraSTEM 2026: `campaigns/mentorias-cierre-2026`.

## Qué necesitas

1. Python 3.11 o más nuevo. En una terminal:

       python3 --version

2. Una contraseña de aplicación de Gmail, no la contraseña normal de la cuenta.

   Cuenta de Google, Seguridad, Verificación en dos pasos, Contraseñas de aplicaciones, Crear.

   Cópiala con los espacios, así: `abcd efgh ijkl mnop`.

## Preparar el programa (una sola vez)

Abre una terminal en esta carpeta y escribe:

    python3 -m venv .venv
    .venv/bin/pip install -e .

Copia el archivo de ejemplo y pon tus datos:

    cp .env.example .env

Abre `.env` y completa las dos líneas:

    EMAIL_ADDRESS=cuenta@gmail.com
    EMAIL_PASSWORD=abcd efgh ijkl mnop

Ese archivo no se sube a GitHub. No lo compartas.

En la hoja de Google, Compartir, Cualquier persona con el enlace, Lector. El nombre de la pestaña y las columnas están en `campaigns/mentorias-cierre-2026/campaign.toml`. Hoy la pestaña se llama `bodega` y las columnas son `Email`, `Nombre`, `Carrera`, `Institucion`.

## Ver la carta sin enviarla

    .venv/bin/pymail preview campaigns/mentorias-cierre-2026

Esto no manda ningún correo. Muestra cuántas personas hay, los correos repetidos, los que no parecen un email, las primeras cinco personas con su correo, nombre, carrera e institución, y una carta de muestra.

## Probar con un solo correo

En `.env` ya tienen que estar el Gmail y la contraseña de aplicación. Este comando manda una sola carta a la dirección que escribas, usando los datos de la primera fila de la hoja:

    .venv/bin/pymail send campaigns/mentorias-cierre-2026 --limit 1 --to tu@gmail.com

Ese envío de prueba no copia las direcciones de `cc` y no se escribe en `sends.db`, así que puedes repetirlo y la lista real sigue pendiente. También se envía cuando toda la lista ya fue mandada. Revisa que haya llegado bien antes de mandar el resto.

## Enviar la lista

    .venv/bin/pymail send campaigns/mentorias-cierre-2026

Entre un correo y el siguiente el programa espera 2 segundos. Si se corta a la mitad, vuelve a ejecutar el mismo comando: no repite los que ya se enviaron. El registro queda en `sends.db` en esta carpeta. Ese archivo tampoco se sube a GitHub.

En la terminal, cada persona se ve así:

    Sending to Ana at ana@example.com
    Sent to Ana at ana@example.com

## Otra campaña

Copia la carpeta `campaigns/mentorias-cierre-2026`, cambia el `id`, el asunto, la hoja y los dos archivos `body.html` y `body.txt`. En el HTML y en el texto, `$header_block` es el lugar del nombre, la carrera y la institución. Si los tres están vacíos, ese bloque no aparece.

Para que otras personas reciban copia, escribe sus correos en `cc` dentro de `campaign.toml`. Si no quieres copias, déjalo así: `cc = []`.
