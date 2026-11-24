# PLANET-IA

> Branch de desenvolvimento comercial. A configuração desta versão, autenticação e homologação estão no [CHANGELOG](CHANGELOG.md).

<img width="1200" height="655" alt="PlantIA" src="https://github.com/user-attachments/assets/cc8c9c52-1a06-4704-818b-60c9afd33cec" />

Aplicación web para identificar plantas a partir de fotografías usando **Google Gemini**. Guarda cada identificación en una base de datos local SQLite para consultarla después.

PlantIA crea un pequeño cuaderno digital de tus plantas. Identifica cada ejemplar mediante IA, almacena sus fotografías y reúne en un solo lugar la información necesaria para cuidarlo.

PlantIA está pensada para identificar y cuidar plantas de la forma más sencilla posible. La aplicación prioriza la facilidad de uso frente a la complejidad.

## Funcionalidades

- Subir fotos de plantas (JPEG, PNG, WebP)
- Identificación automática con Gemini Vision
- Guía de cultivo orientada a principiantes y usuarios avanzados
- Historial consultable con búsqueda por nombre o familia
- Cuaderno de observaciones por planta (anotaciones personales tras cada identificación)
- Calendario lunar en la ficha de cada planta
- API REST para integraciones futuras
- App Android en LAN (CameraX + API REST): identificación, cuaderno, recordatorios y más — ver [android/README.md](android/README.md)

## Qué información obtiene de cada imagen

Al subir una fotografía, PlantIA envía la imagen a **Gemini Vision** y guarda una ficha completa en la base de datos local. La información se muestra en la pantalla de resultado y en la ficha detallada de cada planta.

Cada planta queda registrada en tu colección personal junto con su fotografía, cuidados, notas y recomendaciones. Con el tiempo PlantIA se convierte en un cuaderno digital de todas tus plantas.

### Identificación básica

<p align="center">

  <img width="1066" height="653" alt="identificar" src="https://github.com/user-attachments/assets/60572b57-7eed-4138-b129-c3c4acee0f5b" />

</p>


| Campo | Descripción |
|-------|-------------|
| Nombre común | Nombre popular de la planta en español |
| Nombre científico | Nomenclatura binomial (género y especie) |
| Familia | Familia botánica |
| Tipo | Categoría general (suculenta, árbol, hierba, arbusto, trepadora, etc.) |
| Descripción | Breve texto descriptivo de la planta |
| Confianza | Nivel estimado de certeza: `alto`, `medio` o `bajo` |

### Taxonomía y ayuda a la identificación

<p align="center">
<img width="964" height="629" alt="listado" src="https://github.com/user-attachments/assets/68b0dc4e-23ea-4ecd-af3d-a8653ccda77d" />
</p>

Cuando la identificación no es totalmente segura, PlantIA aporta contexto adicional:

| Campo | Descripción |
|-------|-------------|
| Taxonomía | Reino, orden, familia, género y especie (cuando es posible) |
| Rasgos observados | Lista de características visibles que justifican la identificación |
| Preguntas para mejorar | Preguntas al usuario para afinar el resultado (si la confianza es baja) |
| Candidatos | Hasta 5 plantas alternativas con nombre, razón y nivel de confianza |
| Imágenes de candidatos | Miniaturas automáticas obtenidas por nombre científico (Wikipedia) |

Los candidatos se muestran como **tarjetas con imagen** en la ficha completa de la planta.

### Guía para empezar (principiantes)

| Campo | Descripción |
|-------|-------------|
| Pasos iniciales | 5–8 acciones sencillas para empezar a cuidar la planta hoy |
| Errores comunes | 3–6 errores frecuentes y cómo evitarlos |

### Cuidados

| Campo | Descripción |
|-------|-------------|
| Riego | Frecuencia y cantidad recomendada |
| Luz | Necesidades de exposición (pleno sol, sombra parcial, etc.) |
| Temperatura | Rango de temperatura ideal |
| Humedad | Necesidades de humedad ambiental |
| Suelo | Tipo de sustrato recomendado |
| Fertilización | Cuándo y cómo fertilizar |
| Problemas comunes | Plagas, enfermedades o problemas frecuentes de cultivo |
| Plagas habituales | Insectos y plagas que suelen afectar a esta planta |

### Características y mantenimiento

| Campo | Descripción |
|-------|-------------|
| Dificultad | Nivel de cuidado: fácil, media o difícil |
| Tamaño adulto | Altura y anchura aproximadas en condiciones normales |
| Crecimiento | Ritmo y tipo de crecimiento |
| Floración | Si florece, color y época aproximada |
| Época de poda | Cuándo y cómo podar |
| Época de trasplante | Mejor momento y frecuencia orientativa |
| Señales de trasplante | Indicadores de que necesita cambiar de maceta |
| Maceta y sustrato | Recomendación de maceta (tamaño, material, drenaje) y sustrato |

### Seguridad para mascotas

| Campo | Descripción |
|-------|-------------|
| Toxicidad perros | Nivel de toxicidad y síntomas posibles |
| Toxicidad gatos | Nivel de toxicidad y síntomas posibles |

### Datos adicionales en la interfaz

<p align="center">

  <img width="1070" height="1830" alt="ficha" src="https://github.com/user-attachments/assets/e123feba-21df-483b-bcf5-e08b40a07766" />

</p>

| Elemento | Descripción |
|----------|-------------|
| Calendario lunar | Fase lunar actual, fecha e iluminación estimada (en la ficha) |
| Cuaderno de observaciones | Anotaciones personales (riego, trasplante, floración, etc.) — una línea por evento |
| Fotografía | Imagen original guardada en `~/.plantia/uploads/` |

### Limitaciones

- La identificación es **orientativa**: Gemini puede equivocarse, especialmente con plantas muy similares o fotos de baja calidad.
- Las plantas identificadas **antes de una actualización** pueden no tener todos los campos nuevos (aparecerán vacíos).
- Las miniaturas de candidatos dependen de la disponibilidad de imágenes en Wikipedia.

## Personalizar el prompt de la IA

El texto que se envía a Gemini para analizar cada imagen está definido en:

```
plantia/services/gemini_service.py
```

Busca la constante `PROMPT` al inicio del archivo. Ahí puedes modificar:

- Las instrucciones al modelo (rol, idioma, reglas de comportamiento)
- La estructura JSON que debe devolver
- Los campos que se solicitan (cuidados, características, candidatos, etc.)

Si añades o cambias campos en el prompt, también debes actualizar:

| Archivo | Para qué |
|---------|----------|
| `plantia/schemas/planta.py` | Esquemas Pydantic que validan la respuesta de Gemini |
| `plantia/models/planta.py` | Columnas de la base de datos SQLite |
| `plantia/database.py` | Migración automática de columnas nuevas (`_PLANTAS_COLUMN_MIGRATIONS`) |
| `plantia/services/planta_service.py` | Mapeo de la respuesta de Gemini al modelo de datos |
| `plantia/templates/detalle.html` | Visualización en la ficha de la planta |

El modelo de Gemini se configura en **Configuración** (interfaz web) o con la variable `GEMINI_MODEL` en `.env`. El valor por defecto es `gemini-2.5-flash`.

## Requisitos

- Python 3.10 o superior
- SQLite 3.35 o superior
- Conexión a internet (solo al identificar plantas)
- Clave de API de [Google AI Studio](https://aistudio.google.com/apikey)

## Instalación rápida

```bash
cd PlantIA
python3 run_app.py
```

Abre [http://localhost:8000](http://localhost:8000) en el navegador.

Para identificar plantas, configura la variable del servidor `GEMINI_API_KEY` con una clave de prueba. Puedes copiar `.env.example` a un archivo local `.env` excluido de Git. Crea una cuenta e inicia sesión desde la interfaz web.

## Configuración

| Variable | Descripción |
|----------|-------------|
| `GEMINI_API_KEY` | Clave de Google AI Studio, solo en el servidor |
| `GEMINI_MODEL` | Modelo de Gemini, por defecto `gemini-2.5-flash` |
| `PLANTIA_PORT` | Puerto del iniciador local, por defecto `8000` |
| `PLANET_DATA_DIR` | Directorio con SQLite y fotografías, por defecto `~/.plantia` |
| `PLANET_PUBLIC_ORIGIN` | Origen HTTPS del entorno, necesario para recuperación de contraseña |
| `PLANET_RESEND_API_KEY`, `PLANET_RESEND_FROM` | Verificação de e-mail e recuperação de senha via Resend. Consulte o [guia de homologação](docs/HOMOLOGACAO-RAILWAY.md). |

## Datos locales

El banco de datos y las fotos se guardan por defecto en `~/.plantia/`:

```
~/.plantia/
├── plantia.db      # Base de datos SQLite
└── uploads/        # Fotografías subidas
```

### Copia de seguridad

Para hacer backup, detén la escritura y copia la carpeta de datos completa:

```bash
cp -r ~/.plantia ~/backup-plantia-$(date +%Y%m%d)
```

## API REST

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/plantas/identificar` | Sube imagen, identifica y guarda |
| `GET` | `/api/plantas?q=&page=&page_size=&orden=` | Listado con búsqueda y orden (`recientes`, `antiguas`, `nombre`, `confianza`) |
| `GET` | `/api/plantas/{id}` | Detalle de una planta |
| `PATCH` | `/api/plantas/{id}` | Actualizar notas (`{"notas_usuario": "..."}`) |
| `POST` | `/api/plantas/{id}/notas` | Guardar notas del cuaderno (mismo cuerpo JSON; útil para la app Android) |
| `DELETE` | `/api/plantas/{id}` | Eliminar planta |

Entrega el token de sesión por el encabezado Authorization en las solicitudes API. Puedes obtenerlo iniciando sesión con `POST /api/auth/login` y un formulario con `email` y `password`. Ejemplo con `curl`:

```bash
curl -X POST http://localhost:8000/api/plantas/identificar \
  -H "Authorization: Bearer $PLANET_TOKEN" \
  -F "file=@mi-planta.jpg"
```

## App Android

<p align="center">

  <img width="1080" height="2392" alt="Screenshot_2026-07-10-20-44-44-728_com plantia" src="https://github.com/user-attachments/assets/5ec7b49a-6c4d-4b50-b5c8-377a496060e7" />

</p>

Cliente móvil en Kotlin + Jetpack Compose para usar PlantIA en la red local. Documentación completa en [android/README.md](android/README.md).

| Función | Descripción |
|---------|-------------|
| Identificar | Cámara CameraX o **elegir de galería** |
| Re-identificar | Nueva foto para afinar una planta ya guardada |
| Mis plantas | Grid con búsqueda, orden, paginación y **swipe «Regada hoy»** |
| Ficha completa | Cuidados, calendario lunar, toxicidad, plagas, mantenimiento, candidatos |
| Cuaderno | Timeline, chips rápidos y sincronización con el servidor |
| Recordatorios | Riego cada 1–14 días con **hora del aviso** y panel «regar hoy» |
| Ajustes | URL del servidor, **tema claro/oscuro/sistema** y pantalla Acerca de |

Compilación:

```bash
cd android/PlantIAAndroid
./gradlew assembleDebug
```

## Arranque manual (con venv activo)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
PLANET_INSECURE_LOCAL_HTTP=1 uvicorn main:app --host 127.0.0.1 --reload --port 8000
```

## Aviso

La identificación por IA es **orientativa**. Gemini puede equivocarse, especialmente con plantas muy similares o fotos de baja calidad. El campo de confianza (`alto`, `medio`, `bajo`) indica la certeza estimada.

## Licencia

GNU GPL v3.0

### Homologação comercial

Use um banco separado por meio de `PLANET_DATA_DIR` e configure `PLANET_PUBLIC_ORIGIN`
com a origem HTTPS da homologação. Crie uma conta nesse ambiente e habilite o primeiro
administrador a partir do identificador numérico da conta, usando o mesmo diretório de dados.

```bash
python -m scripts.commercial_bootstrap ID_DA_CONTA
```

Abra `/admin/comercial` para configurar franquias mensais, custos estimados, mercados,
preços, funções de usuário e acesso aos recursos de IA. Para habilitar o Checkout,
crie os preços recorrentes mensal e anual no Stripe em modo de teste e associe os
IDs `price_…` aos respectivos planos no painel. Configure o Customer Portal de teste
no Stripe com os preços habilitados e as opções de mudança e cancelamento.

Defina `PLANET_STRIPE_KEY` com uma chave de teste e `PLANET_STRIPE_WEBHOOK_SECRET`
com o segredo de teste do endpoint `/api/stripe/webhook`. O endpoint recebe
`customer.subscription.created`, `customer.subscription.updated`,
`customer.subscription.deleted`, `customer.subscription.paused` e
`customer.subscription.resumed`. O Checkout exige uma chave de teste. O webhook
rejeita eventos de produção. Use credenciais somente no ambiente de homologação.

O catálogo é selecionado por mercado e a receita recorrente estimada é exibida por
moeda. A margem em BRL desconta o custo estimado de IA e dispensa conversão das
demais moedas. Os limites mensais seguem UTC. O Android exibe a franquia e o plano
com dados do servidor. A integração de compra e validação de recibos da Play Store
e da App Store exige implementação específica antes de habilitar vendas nas lojas.

O roteiro de [homologação isolada no Railway](docs/HOMOLOGACAO-RAILWAY.md)
inclui a instalação do APK, a autorização GitHub e os testes com provedores
reais de homologação. Consulte também o [checklist de lançamento web](docs/CHECKLIST-LANCAMENTO.md).
