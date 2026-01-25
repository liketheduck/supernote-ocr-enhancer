#!/usr/bin/env python3
"""
Test script for Logseq flat export functionality.

This script tests the new flat structure functions with various path scenarios.
"""

from pathlib import Path
import sys
import os
import re

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Import just the functions we need without dependencies
def sanitize_filename(name: str) -> str:
    """Sanitize filename for filesystem compatibility."""
    # Remove or replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    # Remove leading/trailing spaces and dots
    name = name.strip('. ')
    return name


def build_flat_filename_from_path(rel_path: Path) -> str:
    """
    Generate a flat filename from a relative path, avoiding conflicts.
    
    Examples:
    - Path('nota.md') -> 'nota.md'
    - Path('ProyectoA/Cliente1/nota1.md') -> 'ProyectoA_Cliente1_nota1.md'
    - Path('AreaX/SubareaY/notaZ.md') -> 'AreaX_SubareaY_notaZ.md'
    
    Args:
        rel_path: Relative path from supernote_export/
        
    Returns:
        Flat filename with path segments joined by underscores
    """
    if len(rel_path.parts) <= 1:
        # Root level file, keep original name
        return rel_path.name
    
    # Join parent directories with underscore, then add filename
    parent_segments = '_'.join(rel_path.parts[:-1])
    filename = rel_path.name
    return f"{parent_segments}_{filename}"


def build_page_properties_from_path(rel_path: Path) -> dict:
    """
    Generate Logseq page properties from a relative path.
    
    Examples:
    - Path('nota.md') -> {'source': 'Supernote', 'path': 'Supernote', 'tags': ['[[Supernote]]']}
    - Path('ProyectoA/Cliente1/nota1.md') -> {
        'source': 'Supernote',
        'path': 'Supernote/ProyectoA/Cliente1',
        'tags': ['[[Supernote]]', '[[Supernote/ProyectoA]]', '[[Supernote/ProyectoA/Cliente1]]']
      }
    
    Args:
        rel_path: Relative path from supernote_export/
        
    Returns:
        Dictionary with source, path, and tags properties
    """
    # Remove file extension to get folder path
    if len(rel_path.parts) <= 1:
        # Root level file
        path_segments = []
    else:
        path_segments = list(rel_path.parts[:-1])  # All parts except filename
    
    # Build path property
    path_property = "Supernote"
    if path_segments:
        path_property += "/" + "/".join(path_segments)
    
    # Build cumulative tags
    tags = ["[[Supernote]]"]
    cumulative_path = "Supernote"
    for segment in path_segments:
        cumulative_path += "/" + segment
        tags.append(f"[[{cumulative_path}]]")
    
    return {
        'source': 'Supernote',
        'path': path_property,
        'tags': tags
    }


def merge_properties_with_content(content: str, properties: dict) -> str:
    """
    Merge properties into the first property block of Logseq content.
    
    If no property block exists, creates one at the beginning.
    Preserves existing properties and adds/updates source, path, tags.
    
    Args:
        content: Existing markdown content
        properties: Dictionary of properties to add/update
        
    Returns:
        Content with merged properties
    """
    lines = content.split('\n')
    property_start = -1
    property_end = -1
    existing_properties = {}
    
    # Find existing property block (lines with "key:: value" pattern)
    for i, line in enumerate(lines):
        if '::' in line and line.strip():
            if property_start == -1:
                property_start = i
            # Parse existing property
            key, value = line.split('::', 1)
            existing_properties[key.strip()] = value.strip()
            property_end = i + 1  # Update end as we find properties
        elif property_start != -1 and line.strip() and '::' not in line:
            # Property block ended
            break
        elif property_start != -1 and not line.strip():
            # Empty line within property block - continue
            continue
        else:
            # No property block yet, continue
            continue
    
    # Merge properties (new ones override existing)
    merged_properties = {**existing_properties, **properties}
    
    # Build property block
    property_lines = []
    for key, value in merged_properties.items():
        if key == 'tags' and isinstance(value, list):
            # Tags as comma-separated list
            property_lines.append(f"{key}:: {', '.join(value)}")
        else:
            property_lines.append(f"{key}:: {value}")
    
    # Rebuild content
    if property_start >= 0:
        # Replace existing property block
        before = lines[:property_start]
        after = lines[property_end:]
        
        return '\n'.join(before + property_lines + [''] + after)
    else:
        # Add property block at beginning
        return '\n'.join(property_lines + [''] + lines)


def test_build_flat_filename():
    """Test flat filename generation."""
    print("🧪 Testing build_flat_filename_from_path()")
    print("=" * 50)
    
    test_cases = [
        (Path("nota.md"), "nota.md"),
        (Path("ProyectoA/Cliente1/nota1.md"), "ProyectoA_Cliente1_nota1.md"),
        (Path("AreaX/SubareaY/notaZ.md"), "AreaX_SubareaY_notaZ.md"),
        (Path("A/B/C/D/complex_note.md"), "A_B_C_D_complex_note.md"),
        (Path("single"), "single"),
    ]
    
    for input_path, expected in test_cases:
        result = build_flat_filename_from_path(input_path)
        status = "✅" if result == expected else "❌"
        print(f"{status} {input_path} -> {result}")
        if result != expected:
            print(f"   Expected: {expected}")
    
    print()


def test_build_page_properties():
    """Test page properties generation."""
    print("🧪 Testing build_page_properties_from_path()")
    print("=" * 50)
    
    test_cases = [
        {
            "input": Path("nota.md"),
            "expected": {
                "source": "Supernote",
                "path": "Supernote",
                "tags": ["[[Supernote]]"]
            }
        },
        {
            "input": Path("ProyectoA/Cliente1/nota1.md"),
            "expected": {
                "source": "Supernote",
                "path": "Supernote/ProyectoA/Cliente1",
                "tags": ["[[Supernote]]", "[[Supernote/ProyectoA]]", "[[Supernote/ProyectoA/Cliente1]]"]
            }
        },
        {
            "input": Path("AreaX/SubareaY/notaZ.md"),
            "expected": {
                "source": "Supernote",
                "path": "Supernote/AreaX/SubareaY",
                "tags": ["[[Supernote]]", "[[Supernote/AreaX]]", "[[Supernote/AreaX/SubareaY]]"]
            }
        }
    ]
    
    for case in test_cases:
        input_path = case["input"]
        expected = case["expected"]
        result = build_page_properties_from_path(input_path)
        
        print(f"Input: {input_path}")
        print(f"Result: {result}")
        
        # Check each property
        all_correct = True
        for key, expected_value in expected.items():
            if key not in result or result[key] != expected_value:
                print(f"❌ {key}: expected {expected_value}, got {result.get(key)}")
                all_correct = False
            else:
                print(f"✅ {key}: {result[key]}")
        
        if all_correct:
            print("✅ All properties correct!")
        print()


def test_merge_properties():
    """Test property merging with content."""
    print("🧪 Testing merge_properties_with_content()")
    print("=" * 50)
    
    # Test 1: No existing properties
    content1 = "# Título\n\nEste es el contenido."
    properties1 = {
        "source": "Supernote",
        "path": "Supernote/Test",
        "tags": ["[[Supernote]]", "[[Supernote/Test]]"]
    }
    
    result1 = merge_properties_with_content(content1, properties1)
    print("Test 1: No existing properties")
    print("Result:")
    print(result1)
    print()
    
    # Test 2: Existing properties
    content2 = """existing:: value
author:: John Doe

# Título

Contenido existente."""
    
    properties2 = {
        "source": "Supernote",
        "path": "Supernote/Test",
        "tags": ["[[Supernote]]", "[[Supernote/Test]]"]
    }
    
    result2 = merge_properties_with_content(content2, properties2)
    print("Test 2: Existing properties")
    print("Result:")
    print(result2)
    print()
    
    # Test 3: Override existing property
    content3 = """source:: Old Source
path:: Old Path

# Título"""
    
    properties3 = {
        "source": "Supernote",  # This should override
        "tags": ["[[Supernote]]"]
    }
    
    result3 = merge_properties_with_content(content3, properties3)
    print("Test 3: Override existing property")
    print("Result:")
    print(result3)
    print()


def example_transformation():
    """Show complete example transformations."""
    print("📋 Example Transformations")
    print("=" * 50)
    
    examples = [
        "supernote_export/ProyectoA/Cliente1/nota1.md",
        "supernote_export/AreaX/SubareaY/notaZ.md",
        "supernote_export/simple_note.md"
    ]
    
    for example_path in examples:
        rel_path = Path(example_path).relative_to("supernote_export")
        
        print(f"📁 Original: {example_path}")
        
        # Generate flat filename
        flat_filename = build_flat_filename_from_path(rel_path)
        print(f"📄 Flat filename: {flat_filename}")
        
        # Generate properties
        properties = build_page_properties_from_path(rel_path)
        print(f"🏷️  Properties:")
        for key, value in properties.items():
            if key == 'tags':
                print(f"   {key}: {', '.join(value)}")
            else:
                print(f"   {key}: {value}")
        
        # Show example of final file content
        sample_content = f"""# {rel_path.stem}

Este es el contenido de la nota desde {rel_path}.

## Puntos importantes
- Punto 1
- Punto 2
- Punto 3"""
        
        final_content = merge_properties_with_content(sample_content, properties)
        
        print(f"📝 Final content preview:")
        lines = final_content.split('\n')
        for i, line in enumerate(lines[:10]):  # Show first 10 lines
            print(f"   {line}")
        if len(lines) > 10:
            print(f"   ... ({len(lines) - 10} more lines)")
        
        print("-" * 40)


if __name__ == "__main__":
    print("🚀 Logseq Flat Export Tests")
    print("=" * 60)
    print()
    
    test_build_flat_filename()
    test_build_page_properties()
    test_merge_properties()
    example_transformation()
    
    print("✅ All tests completed!")
