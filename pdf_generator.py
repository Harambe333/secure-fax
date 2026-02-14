from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from datetime import datetime

def generate_fax_pdf(sender_id, recipient_id, message_content, output_filename="fax.pdf"):
    c = canvas.Canvas(output_filename, pagesize=letter)
    width, height = letter
    
    # Header
    c.setLineWidth(3)
    c.line(40, height - 40, width - 40, height - 40)
    c.setFont("Courier-Bold", 28)
    c.drawString(50, height - 80, "FACSIMILE TRANSMITTAL")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 95, "Secure Virtual Fax System")
    
    # Fields
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 150, f"TO: {recipient_id}")
    c.drawString(50, height - 175, f"FROM: {sender_id}")
    c.drawString(50, height - 200, f"DATE: {datetime.now().strftime('%Y-%m-%d')}")
    
    # Message Body
    c.drawString(50, height - 250, "MESSAGE:")
    c.rect(40, 100, width - 80, height - 360)
    
    text_obj = c.beginText(50, height - 280)
    text_obj.setFont("Courier", 11)
    # Basic wrap logic
    lines = simpleSplit(message_content, "Courier", 11, width - 100)
    for line in lines:
        text_obj.textLine(line)
    c.drawText(text_obj)
    
    c.save()
    return output_filename