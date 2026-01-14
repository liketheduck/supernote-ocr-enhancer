# Integración con Logseq

Exporta tus notas de Supernote a tu grafo de conocimiento de Logseq con OCR mejorado, enlaces a PDFs y metadata enriquecida.

## 🎯 Qué Hace

Convierte cada archivo `.note` procesado en:

1. **Página de Logseq** (`.md`) con:
   - Enlace al PDF en assets
   - Metadata (fecha, fuente, confianza OCR)
   - Tags autogeneradas
   - Resumen automático (si >3 páginas)
   - Texto OCR completo con formato

2. **PDF en assets** (copia del PDF exportado)
   - Ubicado en `assets/supernote/...`
   - Mismo nombre y estructura de carpetas

## 📋 Configuración

### 1. Habilitar Exportación a Logseq

Edita tu `.env.local`:

```bash
# Habilitar exportación a Logseq
LOGSEQ_EXPORT_ENABLED=true

# Ruta a tu directorio de páginas de Logseq
# Las páginas se crearán bajo pages/supernote/
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote

# Ruta a tu directorio de assets de Logseq
# Los PDFs se copiarán aquí
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
```

### 2. Exportación de PDF (Opcional)

**Logseq funciona independientemente** - el PDF se genera automáticamente para Logseq incluso si no tienes `OCR_PDF_EXPORT_ENABLED=true`.

#### Opción A: Solo Logseq (más simple)

```bash
# Solo habilitar Logseq
LOGSEQ_EXPORT_ENABLED=true
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets

# PDF export NO necesario
# OCR_PDF_EXPORT_ENABLED=false
```

**Resultado:**
- ✅ PDF se genera automáticamente en `logseq/assets/supernote/`
- ✅ Enlaces funcionan correctamente
- ✅ Más simple (menos configuración)

#### Opción B: Logseq + PDF Export separado (si quieres PDFs en otro lugar)

```bash
# Exportar PDFs a ubicación separada
OCR_PDF_EXPORT_ENABLED=true
OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs

# Logseq
LOGSEQ_EXPORT_ENABLED=true
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
```

**Resultado:**
- ✅ PDF en `~/Documents/SupernotePDFs/` (para backup/compartir)
- ✅ PDF copiado a `logseq/assets/supernote/` (para Logseq)
- ✅ Dos copias del mismo PDF (más espacio, pero más flexible)

### 3. Estructura Completa Recomendada

```bash
# Exportaciones de texto, PDF y Logseq
OCR_TXT_EXPORT_ENABLED=true
OCR_TXT_EXPORT_PATH=~/Documents/SupernoteText

OCR_PDF_EXPORT_ENABLED=true
OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs

LOGSEQ_EXPORT_ENABLED=true
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
```

## 📁 Estructura de Archivos Generada

### Ejemplo: Nota en Supernote

```
Supernote:
/user/Note/Work/Meeting-2026-01-13.note
```

### Archivos Generados

```
TXT:
~/Documents/SupernoteText/user/Note/Work/Meeting-2026-01-13.txt

PDF:
~/Documents/SupernotePDFs/user/Note/Work/Meeting-2026-01-13.pdf

Logseq Markdown:
~/Documents/logseq/pages/supernote/user/Note/Work/Meeting-2026-01-13.md

Logseq PDF Asset:
~/Documents/logseq/assets/supernote/user/Note/Work/Meeting-2026-01-13.pdf
```

## 📝 Formato de Página Logseq

### Ejemplo de Salida

```markdown
- [[📄 ../assets/supernote/user/Note/Work/Meeting-2026-01-13.pdf]]
  - **Fecha procesamiento**: [[Jan 13th, 2026]]
  - **Fuente**: Supernote
  - **Confianza OCR**: 94.2%
  - **Páginas**: 5
  - **Palabras**: 342
  - **Tags**: #supernote #work #meeting
- ## Resumen
  - Reunión de planificación del proyecto Q1 2026. Discusión de objetivos, timeline y asignación de recursos. Acción items identificados para cada miembro del equipo.
- ## Contenido
  - ### Página 1
    - Reunión de Planificación Q1 2026
    - Fecha: 13 de enero, 2026
    - Asistentes: Juan, María, Pedro
  - ### Página 2
    - Objetivos del Trimestre
    - 1. Lanzar nueva funcionalidad X
    - 2. Mejorar performance en 30%
    - 3. Reducir bugs críticos a <5
  - ### Página 3
    - Timeline
    - Enero: Diseño y planificación
    - Febrero: Desarrollo
    - Marzo: Testing y lanzamiento
  - ### Página 4
    - Asignación de Recursos
    - Juan: Backend development
    - María: Frontend + UX
    - Pedro: QA + DevOps
  - ### Página 5
    - Action Items
    - [ ] Juan: Setup CI/CD pipeline
    - [ ] María: Create mockups
    - [ ] Pedro: Define test strategy
```

## 🏷️ Tags Autogeneradas

### Basadas en Estructura de Carpetas

```
Ruta: /user/Note/Work/Projects/Alpha.note
Tags: #supernote #work #projects #alpha
```

### Basadas en Contenido (Heurísticas)

El sistema detecta palabras clave y añade tags relevantes:

- **Meeting**: `#meeting` (detecta: meeting, agenda, minutes)
- **Tasks**: `#tasks` (detecta: todo, task, action item)
- **Ideas**: `#ideas` (detecta: idea, brainstorm, concept)
- **Project**: `#project` (detecta: project, plan, roadmap)

## 📊 Resumen Automático

### Cuándo se Genera

- Solo para notas con **más de 3 páginas**
- Extrae las primeras 2-3 frases del contenido
- Máximo 200 caracteres

### Ejemplo

```markdown
- ## Resumen
  - Reunión de planificación del proyecto Q1 2026. Discusión de objetivos, timeline y asignación de recursos.
```

## 🔗 Enlaces en Logseq

### Enlace al PDF

```markdown
- [[📄 ../assets/supernote/user/Note/Work/Meeting.pdf]]
```

Hace clic en el enlace → Abre el PDF en Logseq

### Enlace a Fecha (Journal)

```markdown
- **Fecha procesamiento**: [[Jan 13th, 2026]]
```

Hace clic → Va a tu journal de ese día

## 🔄 Flujo de Trabajo Completo

### Con Wrapper Manual

```bash
# 1. Ejecutar wrapper
supernote-sync

# 2. Sincronizar notas en Supernote Partner
# (el wrapper espera)

# 3. Cerrar Supernote Partner
# (el wrapper detecta y continúa)

# 4. Procesamiento automático:
#    - OCR con Vision Framework
#    - Genera TXT
#    - Genera PDF
#    - Genera página Logseq
#    - Copia PDF a assets

# 5. Abrir Logseq
# Tus notas ya están en el grafo
```

### Con Cron Automático

```bash
# Configurar cron (una vez)
./scripts/install-ocr-enhancer-launchd.sh

# Luego, automáticamente cada 6 horas:
# - Detecta archivos nuevos/modificados
# - Procesa OCR
# - Exporta a TXT, PDF y Logseq
# - Tus notas aparecen en Logseq
```

## 🎨 Personalización

### Modificar Template de Página

Edita `app/logseq_exporter.py`, función `export_note_to_logseq()`:

```python
# Línea ~140: Construir markdown
lines = []
lines.append(f"- [[📄 {pdf_rel_path}]]")
# Añade tus propios campos aquí
lines.append(f"  - **Tu campo**: {tu_valor}")
```

### Mejorar Generación de Tags

Edita `app/logseq_exporter.py`, función `generate_tags()`:

```python
# Línea ~40: Añadir más detección de keywords
if 'tu_keyword' in text_lower:
    tags.append('tu-tag')
```

### Mejorar Resumen

Actualmente usa extracción simple de frases. Para mejorar:

**Opción 1: Usar LLM (Qwen)**

```python
# En generate_summary()
# Llamar al OCR API con prompt de resumen
summary = ocr_client.generate_summary(ocr_text)
```

**Opción 2: Usar biblioteca de NLP**

```python
# Instalar: pip install sumy
from sumy.summarizers.lsa import LsaSummarizer
# Generar resumen extractivo
```

## 📈 Casos de Uso

### 1. Notas de Reuniones

```
Supernote → OCR → Logseq
- Tags: #meeting #work
- Enlace a PDF para referencia
- Búsqueda full-text en Logseq
- Enlaces bidireccionales con otros proyectos
```

### 2. Diario Personal

```
Supernote → OCR → Logseq
- Tags: #journal #personal
- Enlace automático a journal del día
- Búsqueda por fecha
- Revisión de entradas pasadas
```

### 3. Ideas y Brainstorming

```
Supernote → OCR → Logseq
- Tags: #ideas #brainstorm
- Conexión con otros conceptos
- Evolución de ideas a lo largo del tiempo
- Exportar a otros formatos desde Logseq
```

### 4. Apuntes de Estudio

```
Supernote → OCR → Logseq
- Tags: #study #course-name
- Organización por tema
- Flashcards en Logseq
- Repaso espaciado
```

## 🐛 Troubleshooting

### Las páginas no aparecen en Logseq

**Problema**: Archivos `.md` creados pero no visibles en Logseq

**Solución**:
1. Verifica que `LOGSEQ_PAGES_PATH` apunta a tu grafo correcto
2. Reindexar en Logseq: `Cmd+Shift+R` o menú "Re-index"
3. Verificar permisos de archivos: `ls -la ~/Documents/logseq/pages/supernote/`

### Los enlaces al PDF no funcionan

**Problema**: Click en enlace no abre el PDF

**Solución**:
1. Verifica que el PDF existe: `ls ~/Documents/logseq/assets/supernote/`
2. Verifica la ruta relativa en el `.md`
3. Asegúrate de que `OCR_PDF_EXPORT_ENABLED=true`

### Tags no se generan correctamente

**Problema**: Solo aparece `#supernote`, faltan otras tags

**Solución**:
1. Revisa los logs: `tail -f data/cron-ocr.log`
2. Verifica que el contenido OCR tiene texto: `cat archivo.txt`
3. Personaliza `generate_tags()` para tu contenido específico

### Resumen no se genera

**Problema**: Notas con >3 páginas no tienen resumen

**Solución**:
1. Verifica que el OCR extrajo texto: `cat archivo.txt`
2. Revisa logs de exportación
3. Ajusta `generate_summary()` si el formato no es compatible

## 🔮 Futuras Mejoras

### Planeadas

- [ ] Resumen con LLM (Qwen) para mejor calidad
- [ ] Detección de TODOs y conversión a tasks de Logseq
- [ ] Detección de fechas y creación de journal links
- [ ] Extracción de entidades (personas, lugares, conceptos)
- [ ] Sugerencias de enlaces a páginas existentes
- [ ] Detección de idioma y metadata multilingüe

### Contribuciones Bienvenidas

Si implementas alguna mejora, considera contribuir al proyecto:
1. Fork del repositorio
2. Implementa tu feature
3. Añade tests
4. Pull request con descripción detallada

## 📚 Referencias

- [Logseq Documentation](https://docs.logseq.com/)
- [Logseq Markdown Format](https://docs.logseq.com/#/page/markdown)
- [Supernote OCR Enhancer README](../README.md)
- [PDF Export Documentation](./PDF_EXPORT.md)

## 💬 Soporte

Si tienes problemas o sugerencias:
1. Revisa los logs: `tail -f data/cron-ocr.log`
2. Verifica la configuración en `.env.local`
3. Abre un issue en GitHub con detalles y logs
