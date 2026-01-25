# Logseq Flat Export - Technical Documentation

## Overview

The Logseq export functionality has been refactored to use a **flat file structure** while preserving the original hierarchy through page properties.

## Key Changes

### Before (Hierarchical)
```
logseq/pages/
├── ProyectoA/
│   └── Cliente1/
│       ├── nota1.md
│       └── nota2.md
└── ProyectoB/
    └── nota3.md
```

### After (Flat with Properties)
```
logseq/pages/
├── ProyectoA_Cliente1_nota1.md
├── ProyectoA_Cliente1_nota2.md
└── ProyectoB_nota3.md
```

Each file contains properties that preserve the original hierarchy:

```markdown
source:: Supernote
path:: Supernote/ProyectoA/Cliente1
tags:: [[Supernote]], [[Supernote/ProyectoA]], [[Supernote/ProyectoA/Cliente1]]

# Original Content
...
```

## Core Functions

### `build_flat_filename_from_path(rel_path: Path) -> str`

Converts a relative path to a flat filename by joining directory segments with underscores.

**Examples:**
- `Path("nota.md")` → `"nota.md"`
- `Path("ProyectoA/Cliente1/nota1.md")` → `"ProyectoA_Cliente1_nota1.md"`
- `Path("AreaX/SubareaY/notaZ.md")` → `"AreaX_SubareaY_notaZ.md"`

### `build_page_properties_from_path(rel_path: Path) -> dict`

Generates Logseq page properties from a relative path.

**Output structure:**
```python
{
    "source": "Supernote",
    "path": "Supernote/ProyectoA/Cliente1",
    "tags": ["[[Supernote]]", "[[Supernote/ProyectoA]]", "[[Supernote/ProyectoA/Cliente1]]"]
}
```

### `merge_properties_with_content(content: str, properties: dict) -> str`

Merges properties into the first property block of Logseq content without breaking existing properties.

**Behavior:**
- If no property block exists → creates one at the beginning
- If properties exist → merges with new ones overriding
- Preserves all existing properties

## Transformation Examples

### Example 1: Nested Path
```
Input: supernote_export/ProyectoA/Cliente1/nota1.md
Output: logseq/pages/ProyectoA_Cliente1_nota1.md
Properties:
  source:: Supernote
  path:: Supernote/ProyectoA/Cliente1
  tags:: [[Supernote]], [[Supernote/ProyectoA]], [[Supernote/ProyectoA/Cliente1]]
```

### Example 2: Simple Path
```
Input: supernote_export/simple_note.md
Output: logseq/pages/simple_note.md
Properties:
  source:: Supernote
  path:: Supernote
  tags:: [[Supernote]]
```

## Benefits

1. **Flat Structure**: All files in one directory - easier for backup and sync
2. **Hierarchy Preserved**: Original structure maintained in properties
3. **Logseq Native**: Uses Logseq's property format and tag namespaces
4. **Searchable**: Tags enable powerful search and filtering
5. **Conflict Resolution**: Automatic unique naming for path conflicts

## Implementation Details

### Property Format
Uses Logseq's native property format (not YAML):
```
key:: value
```

### Tag Namespaces
Uses nested tag syntax for hierarchy:
- `[[Supernote]]` - Root level
- `[[Supernote/ProyectoA]]` - First level
- `[[Supernote/ProyectoA/Cliente1]]` - Second level

### Backwards Compatibility
The original `export_note_to_logseq()` function now redirects to the new flat version for compatibility.

## Testing

Run the test suite to verify functionality:

```bash
./test_logseq_flat.py
```

The tests cover:
- Filename generation
- Property building
- Property merging
- Complete transformation examples
