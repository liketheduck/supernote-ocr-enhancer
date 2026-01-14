# Flujo de Exportación: PDF y Logseq

Diagrama visual de cómo funciona la exportación de PDFs con y sin Logseq.

## 🔄 Escenario 1: Solo PDF Export

```
┌─────────────────────────────────────────────────────────────┐
│  Configuración:                                             │
│  OCR_PDF_EXPORT_ENABLED=true                                │
│  OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs              │
│  LOGSEQ_EXPORT_ENABLED=false                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Procesamiento OCR                                          │
│  - Extrae páginas del .note                                 │
│  - Envía a Vision Framework                                 │
│  - Obtiene resultados OCR                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Exportación PDF                                            │
│  ✅ Genera PDF en ~/Documents/SupernotePDFs/Work/Meeting.pdf│
└─────────────────────────────────────────────────────────────┘
                            ↓
                        ✅ FIN
```

**Resultado:**
- 1 archivo PDF en `~/Documents/SupernotePDFs/`
- No se genera nada para Logseq

---

## 🔄 Escenario 2: Solo Logseq Export

```
┌─────────────────────────────────────────────────────────────┐
│  Configuración:                                             │
│  OCR_PDF_EXPORT_ENABLED=false                               │
│  LOGSEQ_EXPORT_ENABLED=true                                 │
│  LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote       │
│  LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Procesamiento OCR                                          │
│  - Extrae páginas del .note                                 │
│  - Envía a Vision Framework                                 │
│  - Obtiene resultados OCR                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Exportación Logseq                                         │
│  ✅ Genera PDF en ~/logseq/assets/supernote/Work/Meeting.pdf│
│  ✅ Genera MD en ~/logseq/pages/supernote/Work/Meeting.md   │
│     (con enlace a ../assets/supernote/Work/Meeting.pdf)     │
└─────────────────────────────────────────────────────────────┘
                            ↓
                        ✅ FIN
```

**Resultado:**
- 1 archivo PDF en `~/Documents/logseq/assets/supernote/`
- 1 archivo MD en `~/Documents/logseq/pages/supernote/`
- Enlace funciona correctamente

---

## 🔄 Escenario 3: PDF Export + Logseq Export

```
┌─────────────────────────────────────────────────────────────┐
│  Configuración:                                             │
│  OCR_PDF_EXPORT_ENABLED=true                                │
│  OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs              │
│  LOGSEQ_EXPORT_ENABLED=true                                 │
│  LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote       │
│  LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Procesamiento OCR                                          │
│  - Extrae páginas del .note                                 │
│  - Envía a Vision Framework                                 │
│  - Obtiene resultados OCR                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Exportación PDF                                            │
│  ✅ Genera PDF en ~/Documents/SupernotePDFs/Work/Meeting.pdf│
│  📝 Guarda ruta: pdf_path = /path/to/SupernotePDFs/...      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Exportación Logseq                                         │
│  ✅ Copia PDF a ~/logseq/assets/supernote/Work/Meeting.pdf  │
│     (desde pdf_path)                                        │
│  ✅ Genera MD en ~/logseq/pages/supernote/Work/Meeting.md   │
│     (con enlace a ../assets/supernote/Work/Meeting.pdf)     │
└─────────────────────────────────────────────────────────────┘
                            ↓
                        ✅ FIN
```

**Resultado:**
- 1 archivo PDF en `~/Documents/SupernotePDFs/` (original)
- 1 archivo PDF en `~/Documents/logseq/assets/supernote/` (copia)
- 1 archivo MD en `~/Documents/logseq/pages/supernote/`
- Enlace funciona correctamente
- **2 copias del mismo PDF** (más espacio, pero más flexible)

---

## 📊 Comparación de Escenarios

| Configuración | PDF en SupernotePDFs | PDF en Logseq Assets | MD en Logseq | Total PDFs |
|---------------|---------------------|---------------------|--------------|------------|
| **Solo PDF** | ✅ | ❌ | ❌ | 1 |
| **Solo Logseq** | ❌ | ✅ | ✅ | 1 |
| **Ambos** | ✅ | ✅ (copia) | ✅ | 2 |

## 🎯 Recomendaciones

### Para Usuarios de Logseq

**Opción Simple (Recomendada):**
```bash
LOGSEQ_EXPORT_ENABLED=true
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
```

**Ventajas:**
- ✅ Menos configuración
- ✅ Solo 1 copia del PDF (ahorra espacio)
- ✅ Todo en Logseq

**Desventajas:**
- ❌ No tienes PDFs fuera de Logseq para compartir

---

**Opción Completa:**
```bash
OCR_PDF_EXPORT_ENABLED=true
OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs

LOGSEQ_EXPORT_ENABLED=true
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
```

**Ventajas:**
- ✅ PDFs en ubicación separada (fácil compartir/backup)
- ✅ PDFs en Logseq (para enlaces)
- ✅ Máxima flexibilidad

**Desventajas:**
- ❌ 2 copias del mismo PDF (usa más espacio)
- ❌ Más configuración

---

### Para Usuarios Sin Logseq

```bash
OCR_PDF_EXPORT_ENABLED=true
OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs
```

**Ventajas:**
- ✅ Simple
- ✅ Solo 1 copia del PDF
- ✅ Fácil compartir

---

## 🔍 Detalles Técnicos

### Código Relevante (main.py)

```python
# Línea 356-369: Exportación PDF
pdf_path = None
if OCR_PDF_EXPORT_ENABLED and OCR_PDF_EXPORT_PATH and page_results:
    pdf_path = export_note_to_pdf(...)  # Genera PDF
    # pdf_path ahora contiene la ruta al PDF generado

# Línea 372-381: Exportación Logseq
if LOGSEQ_EXPORT_ENABLED and LOGSEQ_PAGES_PATH and LOGSEQ_ASSETS_PATH:
    export_note_to_logseq(
        ...
        pdf_source_path=pdf_path  # Pasa la ruta (o None)
    )
```

### Código Relevante (logseq_exporter.py)

```python
# Línea 175-195: Manejo del PDF
if pdf_source_path and pdf_source_path.exists():
    # Caso 1: PDF ya existe (generado por OCR_PDF_EXPORT)
    shutil.copy2(pdf_source_path, pdf_asset_path)
else:
    # Caso 2: PDF no existe, generarlo directamente
    export_note_to_pdf(
        note_path,
        page_results,
        supernote_data_path,
        logseq_assets_path / "supernote"
    )
```

### Flujo de Decisión

```
¿pdf_source_path existe?
    ├─ SÍ → Copiar PDF existente a Logseq assets
    └─ NO → Generar PDF directamente en Logseq assets
```

---

## ❓ FAQ

**P: ¿Necesito `OCR_PDF_EXPORT_ENABLED=true` para usar Logseq?**  
R: **NO**. Logseq genera su propio PDF automáticamente si no existe.

**P: ¿Qué pasa si tengo ambos habilitados?**  
R: Se generan 2 copias del PDF (una en `SupernotePDFs`, otra en `logseq/assets`).

**P: ¿Cuál es más eficiente?**  
R: Solo Logseq (1 PDF generado). Con ambos se genera 1 PDF y se copia 1 vez.

**P: ¿Puedo cambiar de configuración después?**  
R: Sí, pero los archivos ya generados no se mueven automáticamente.

**P: ¿Cómo elimino PDFs duplicados?**  
R: Decide qué ubicación prefieres y borra la otra manualmente.
