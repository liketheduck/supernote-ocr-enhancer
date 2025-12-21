#!/usr/bin/env python3
"""
Compare OCR before/after JSON files and generate a report.
"""

import json
import sys
from pathlib import Path

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def compare_ocr(before_path, after_path, output_path=None):
    before = load_json(before_path)
    after = load_json(after_path)
    
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("SUPERNOTE OCR COMPARISON REPORT")
    report_lines.append("=" * 80)
    report_lines.append(f"Before: {before_path}")
    report_lines.append(f"After:  {after_path}")
    report_lines.append("")
    
    # Summary stats
    total_before_chars = 0
    total_after_chars = 0
    total_before_pages_with_ocr = 0
    total_after_pages_with_ocr = 0
    
    for file_path in sorted(set(before.keys()) | set(after.keys())):
        b = before.get(file_path, {})
        a = after.get(file_path, {})
        
        b_chars = b.get('total_text_length', 0)
        a_chars = a.get('total_text_length', 0)
        b_pages = b.get('pages_with_ocr', 0)
        a_pages = a.get('pages_with_ocr', 0)
        
        total_before_chars += b_chars
        total_after_chars += a_chars
        total_before_pages_with_ocr += b_pages
        total_after_pages_with_ocr += a_pages
    
    report_lines.append("SUMMARY")
    report_lines.append("-" * 40)
    report_lines.append(f"Total files:           {len(before)}")
    report_lines.append(f"Before total chars:    {total_before_chars:,}")
    report_lines.append(f"After total chars:     {total_after_chars:,}")
    change = ((total_after_chars - total_before_chars) / total_before_chars * 100) if total_before_chars > 0 else 0
    report_lines.append(f"Change:                {change:+.1f}%")
    report_lines.append("")
    
    # Per-file comparison
    report_lines.append("PER-FILE COMPARISON")
    report_lines.append("-" * 80)
    
    for file_path in sorted(before.keys()):
        b = before.get(file_path, {})
        a = after.get(file_path, {})
        
        if 'error' in b or 'error' in a:
            continue
            
        b_chars = b.get('total_text_length', 0)
        a_chars = a.get('total_text_length', 0)
        total_pages = b.get('total_pages', 0)
        
        if b_chars == 0 and a_chars == 0:
            continue
            
        change = ((a_chars - b_chars) / b_chars * 100) if b_chars > 0 else (100 if a_chars > 0 else 0)
        
        report_lines.append("")
        report_lines.append(f"FILE: {file_path}")
        report_lines.append(f"  Pages: {total_pages}")
        report_lines.append(f"  Before: {b_chars:,} chars")
        report_lines.append(f"  After:  {a_chars:,} chars")
        report_lines.append(f"  Change: {change:+.1f}%")
        
        # Page-by-page for significant files
        if total_pages <= 20 and (b_chars > 100 or a_chars > 100):
            b_pages = b.get('pages', [])
            a_pages = a.get('pages', [])
            
            report_lines.append("")
            report_lines.append("  Page-by-page:")
            for i in range(total_pages):
                bp = b_pages[i] if i < len(b_pages) else {}
                ap = a_pages[i] if i < len(a_pages) else {}
                
                b_text = bp.get('text', '')[:60].replace('\n', ' ')
                a_text = ap.get('text', '')[:60].replace('\n', ' ')
                b_len = len(bp.get('text', ''))
                a_len = len(ap.get('text', ''))
                
                if b_len > 0 or a_len > 0:
                    report_lines.append(f"    Page {i}: {b_len} -> {a_len} chars")
                    if b_text != a_text[:60]:
                        report_lines.append(f"      Before: {b_text}...")
                        report_lines.append(f"      After:  {a_text}...")
    
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("END OF REPORT")
    report_lines.append("=" * 80)
    
    report = '\n'.join(report_lines)
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"Report saved to: {output_path}")
    
    return report

if __name__ == "__main__":
    import sys

    # Default to data directory relative to script location
    script_dir = Path(__file__).parent.parent
    data_dir = script_dir / "data"

    before_path = data_dir / "ocr-before.json"
    after_path = data_dir / "ocr-after.json"
    output_path = data_dir / "ocr-comparison-report.txt"

    # Allow command line override
    if len(sys.argv) >= 3:
        before_path = Path(sys.argv[1])
        after_path = Path(sys.argv[2])
        if len(sys.argv) >= 4:
            output_path = Path(sys.argv[3])

    report = compare_ocr(before_path, after_path, output_path)
    print(report)
