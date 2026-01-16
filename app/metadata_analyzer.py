"""
AI-powered metadata analysis for Logseq enhancement.
"""

import logging
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class NoteMetadata:
    """Metadata structure for enhanced Logseq front matter."""
    
    def __init__(self, 
                 content_type: str = "Other",
                 content_tags: List[str] = None,
                 language: str = "es",
                 confidence: float = 0.0):
        self.content_type = content_type
        self.content_tags = content_tags or []
        self.language = language
        self.confidence = confidence


class MetadataAnalyzer:
    """AI-powered analysis for note metadata extraction."""
    
    # Content type classification patterns
    CONTENT_TYPES = {
        "Meal-Planning": ["comidas", "menu", "desayuno", "almuerzo", "cena", "food", "meal", "pepas", "pavo", "salmon", "pasta"],
        "Meeting": ["reunión", "meeting", "agenda", "action items", "attendees", "minutes"],
        "Notes": ["apuntes", "notas", "resumen", "puntos", "summary", "notes"],
        "Ideas": ["idea", "concepto", "innovación", "brainstorm", "innovation", "concept"],
        "Planning": ["plan", "planificación", "objetivos", "timeline", "goals", "planning"],
        "Calendar": ["fecha", "agenda", "calendario", "evento", "date", "schedule", "L M X J V S D"],
        "Other": []
    }
    
    # Tag mapping for enhanced discoverability
    TAG_MAPPING = {
        "Meal-Planning": ["Planning/Food", "Calendar", "Nutrition"],
        "Meeting": ["Work/Meetings", "Calendar", "Action-Items"],
        "Notes": ["Learning/Notes", "Reference", "Study"],
        "Ideas": ["Creative/Ideas", "Brainstorm", "Innovation"],
        "Planning": ["Projects/Planning", "Goals", "Timeline"],
        "Calendar": ["Schedule", "Events", "Time-Management"],
        "Other": ["General", "Miscellaneous"]
    }
    
    def __init__(self, ocr_client=None):
        self.ocr_client = ocr_client
    
    def extract_note_date(self, filename: str, content: str) -> Optional[str]:
        """
        Extract date from filename or content.
        
        Args:
            filename: Note filename (e.g., "20251230_Comidas.note")
            content: OCR text content
            
        Returns:
            Date string in YYYY-MM-DD format or None
        """
        # 1. Try to extract from filename (YYYYMMDD pattern)
        date_match = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
        if date_match:
            year, month, day = date_match.groups()
            try:
                # Validate date
                datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
                return f"{year}-{month}-{day}"
            except ValueError:
                pass  # Invalid date, continue with other methods
        
        # 2. Try to extract from content (look for date patterns)
        content_date_patterns = [
            r'(\d{1,2})/(\d{1,2})/(\d{4})',  # DD/MM/YYYY
            r'(\d{4})-(\d{2})-(\d{2})',      # YYYY-MM-DD
            r'(\d{1,2})-(\d{1,2})-(\d{4})',  # DD-MM-YYYY
        ]
        
        for pattern in content_date_patterns:
            matches = re.findall(pattern, content)
            if matches:
                # Take first match
                match = matches[0]
                try:
                    if len(match[0]) == 4:  # YYYY first
                        date_str = f"{match[0]}-{match[1]:02d}-{match[2]:02d}"
                    else:  # DD first
                        date_str = f"{match[2]}-{match[1]:02d}-{match[0]:02d}"
                    
                    # Validate date
                    datetime.strptime(date_str, "%Y-%m-%d")
                    return date_str
                except ValueError:
                    continue
        
        return None
    
    def detect_language(self, content: str) -> str:
        """
        Detect language from content (simple heuristic).
        
        Args:
            content: OCR text content
            
        Returns:
            Language code ('es', 'en', etc.)
        """
        # Simple language detection based on common words
        spanish_words = ["el", "la", "de", "que", "y", "en", "un", "es", "se", "no", "te", "lo", "le", "da", "su", "por", "son", "con", "para", "como", "las", "del", "los", "una", "mi", "me", "si", "ya", "todo", "pero", "más", "hacer", "puede", "ser", "está", "tiempo", "año", "vez", "puede", "forma", "parte", "donde", "bien", "estar", "tener", "hacer", "mismo", "dice", "entre", "cuando", "mucho", "después", "estos", "solo", "han", "sí", "están", "esta", "esto", "todos", "otros", "otras", "otros", "otro"]
        
        english_words = ["the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not", "on", "with", "he", "as", "you", "do", "at", "this", "but", "his", "by", "from", "they", "we", "say", "her", "she", "or", "an", "will", "my", "one", "all", "would", "there", "their", "what", "so", "up", "out", "if", "about", "who", "get", "which", "go", "me", "when", "make", "can", "like", "time", "no", "just", "him", "know", "take", "people", "into", "year", "your", "good", "some", "could", "them", "see", "other", "than", "then", "now", "look", "only", "come", "its", "over", "think", "also", "back", "after", "use", "two", "how", "our", "work"]
        
        content_lower = content.lower()
        spanish_count = sum(1 for word in spanish_words if word in content_lower)
        english_count = sum(1 for word in english_words if word in content_lower)
        
        if spanish_count > english_count:
            return "es"
        elif english_count > spanish_count:
            return "en"
        else:
            return "es"  # Default to Spanish for Supernote context
    
    def classify_content_type(self, content: str, filename: str) -> str:
        """
        Classify content type based on patterns.
        
        Args:
            content: OCR text content
            filename: Note filename
            
        Returns:
            Content type string
        """
        content_lower = content.lower()
        filename_lower = filename.lower()
        
        # Score each content type
        type_scores = {}
        for content_type, keywords in self.CONTENT_TYPES.items():
            score = 0
            
            # Check content keywords
            for keyword in keywords:
                content_matches = content_lower.count(keyword)
                filename_matches = filename_lower.count(keyword)
                score += content_matches * 2 + filename_matches * 3  # Filename weighted higher
            
            type_scores[content_type] = score
        
        # Return type with highest score (excluding "Other" if others have scores)
        sorted_types = sorted(type_scores.items(), key=lambda x: x[1], reverse=True)
        
        if sorted_types[0][0] != "Other" and sorted_types[0][1] > 0:
            return sorted_types[0][0]
        elif sorted_types[1][1] > 0:  # Second best has score
            return sorted_types[1][0]
        else:
            return "Other"
    
    def extract_content_tags(self, content: str, content_type: str) -> List[str]:
        """
        Extract relevant tags from content.
        
        Args:
            content: OCR text content
            content_type: Classified content type
            
        Returns:
            List of relevant tags
        """
        content_lower = content.lower()
        
        # Type-specific tag extraction
        if content_type == "Meal-Planning":
            food_patterns = [
                r'\b(pavo|salmon|pasta|bacalao|cerveza|pepas|mostaza|broccoli|gnocchi)\b',
                r'\b(desayuno|almuerzo|cena|comida)\b',
                r'\b(lunes|martes|miércoles|jueves|viernes|sábado|domingo)\b'
            ]
        elif content_type == "Meeting":
            meeting_patterns = [
                r'\b(reunión|meeting|agenda)\b',
                r'\b(action|decision|acuerdo)\b',
                r'\b(present|attendee|asistente)\b'
            ]
        elif content_type == "Planning":
            planning_patterns = [
                r'\b(plan|objetivo|meta)\b',
                r'\b(plazo|deadline|fecha)\b',
                r'\b(proyecto|task|tarea)\b'
            ]
        else:
            # Generic patterns for other types
            food_patterns = [r'\b\w{4,}\b']  # Words 4+ chars
        
        # Extract tags using patterns
        tags = set()
        all_patterns = food_patterns if content_type == "Meal-Planning" else food_patterns
        
        for pattern in all_patterns:
            matches = re.findall(pattern, content_lower)
            tags.update(matches)
        
        # Filter and normalize tags
        filtered_tags = []
        for tag in tags:
            if len(tag) >= 3 and tag not in ["the", "and", "for", "are", "with", "this", "that"]:
                filtered_tags.append(tag)
        
        return filtered_tags[:5]  # Max 5 tags
    
    def analyze_with_ai(self, content: str, filename: str) -> NoteMetadata:
        """
        Use AI model for enhanced analysis (if available).
        
        Args:
            content: OCR text content
            filename: Note filename
            
        Returns:
            NoteMetadata with AI analysis
        """
        if not self.ocr_client:
            # Fallback to rule-based analysis
            return self.analyze_with_rules(content, filename)
        
        try:
            # Use AI model for analysis
            prompt = f"""Analiza esta nota de Supernote y extrae SOLO:

1. **Tipo de contenido**: Uno de [{", ".join(self.CONTENT_TYPES.keys())}]
2. **Tags temáticos**: 3-5 tags relevantes del contenido

Ejemplos:
- "L M X J V S D 30 31 1 2 3 4 5 6 M30: Pepas Mostaza + Cerveza" → tipo: "Meal-Planning", tags: ["food", "meal-planning", "weekly-menu"]
- "Reunión equipo para discutir proyecto" → tipo: "Meeting", tags: ["work", "team", "project"]

Nota: {filename}
Contenido: {content[:1000]}

Responde JSON exacto: {{"type": "TIPO", "tags": ["tag1", "tag2", "tag3"]}}"""

            # Call AI API
            response = self.ocr_client.session.post(
                f"{self.ocr_client.base_url}/generate",
                json={"prompt": prompt, "max_tokens": 100, "temperature": 0.0},
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            ai_text = result.get("text", "").strip()
            
            # Parse JSON response
            try:
                ai_data = json.loads(ai_text)
                content_type = ai_data.get("type", "Other")
                content_tags = ai_data.get("tags", [])
                
                # Validate content type
                if content_type not in self.CONTENT_TYPES:
                    content_type = "Other"
                
                return NoteMetadata(
                    content_type=content_type,
                    content_tags=content_tags[:5],
                    language=self.detect_language(content),
                    confidence=0.9  # High confidence for AI analysis
                )
                
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse AI response: {ai_text}")
                return self.analyze_with_rules(content, filename)
                
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}, falling back to rules")
            return self.analyze_with_rules(content, filename)
    
    def analyze_with_rules(self, content: str, filename: str) -> NoteMetadata:
        """
        Rule-based analysis fallback.
        
        Args:
            content: OCR text content
            filename: Note filename
            
        Returns:
            NoteMetadata with rule-based analysis
        """
        content_type = self.classify_content_type(content, filename)
        content_tags = self.extract_content_tags(content, content_type)
        language = self.detect_language(content)
        
        return NoteMetadata(
            content_type=content_type,
            content_tags=content_tags,
            language=language,
            confidence=0.7  # Lower confidence for rule-based
        )
    
    def generate_enhanced_tags(self, metadata: NoteMetadata) -> List[str]:
        """
        Generate enhanced tags combining IA analysis with predefined mapping.
        
        Args:
            metadata: NoteMetadata from analysis
            
        Returns:
            List of enhanced tags in Logseq format
        """
        tags = []
        
        # Primary tag (functional)
        primary_tag = f"[[Supernote/{metadata.content_type}]]"
        tags.append(primary_tag)
        
        # Related tags from mapping
        related_tags = self.TAG_MAPPING.get(metadata.content_type, [])
        for tag in related_tags:
            tags.append(f"[[{tag}]]")
        
        # Content-specific tags (max 3)
        content_tags = metadata.content_tags[:3]
        for tag in content_tags:
            tags.append(f"[[{tag}]]")
        
        return tags
    
    def analyze_note(self, content: str, filename: str, use_ai: bool = True) -> Tuple[NoteMetadata, List[str]]:
        """
        Complete analysis pipeline for a note.
        
        Args:
            content: OCR text content
            filename: Note filename
            use_ai: Whether to use AI analysis
            
        Returns:
            Tuple of (NoteMetadata, enhanced_tags)
        """
        if use_ai and self.ocr_client:
            metadata = self.analyze_with_ai(content, filename)
        else:
            metadata = self.analyze_with_rules(content, filename)
        
        enhanced_tags = self.generate_enhanced_tags(metadata)
        
        return metadata, enhanced_tags
