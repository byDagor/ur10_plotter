class TextObject:
    def __init__(self, text, x, y, font_family, font_size, is_bold, is_italic, line_spacing=1.2):
        self.text = text
        self.x = x
        self.y = y
        self.font_family = font_family
        self.font_size = font_size
        self.is_bold = is_bold
        self.is_italic = is_italic
        self.line_spacing = line_spacing

    def __str__(self):
        style = []
        if self.is_bold: style.append("B")
        if self.is_italic: style.append("I")
        style_str = f"[{','.join(style)}]" if style else ""
        return f"{self.text[:15]}... {style_str} ({self.font_family}, {self.font_size}mm, {self.line_spacing}em)"
