from docx import Document

doc = Document('DOCS SIGNALS BUY CRYPTO.docx')
with open('docx_content.txt', 'w', encoding='utf-8') as f:
    for para in doc.paragraphs:
        if para.text.strip():
            f.write(para.text + '\n\n')
print("Saved to docx_content.txt")
