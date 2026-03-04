from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def create_pdf():
    c = canvas.Canvas("test_hausgeld.pdf", pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 750, "Hausgeldabrechnung 2023 - WEG Musterstraße 12")
    
    c.setFont("Helvetica", 12)
    c.drawString(100, 710, "Sehr geehrter Eigentümer, nachfolgend Ihre Abrechnung für das Jahr 2023.")
    
    c.drawString(100, 680, "Gesamtsumme der Ausgaben: 12.500,00 EUR")
    c.drawString(100, 660, "Ihr Anteil: 1.250,50 EUR")
    c.drawString(100, 640, "Bereits gezahlt: 1.200,00 EUR")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, 610, "Abrechnungssaldo (Nachzahlung): 50,50 EUR")
    
    c.setFont("Helvetica", 12)
    c.drawString(100, 570, "Steuerbescheinigung nach §35a EStG:")
    c.drawString(100, 550, " - Haushaltsnahe Dienstleistungen (Gebäudereinigung): 150,20 EUR")
    c.drawString(100, 530, " - Handwerkerleistungen (Malerarbeiten): 320,40 EUR")
    
    c.drawString(100, 490, "Weitere Kosten:")
    c.drawString(100, 470, " - Instandhaltungsrücklage: 300,00 EUR")
    c.drawString(100, 450, " - Verwaltergebühr: 250,00 EUR")
    c.drawString(100, 430, " - Gebäudeversicherung: 80,00 EUR")
    
    c.drawString(100, 390, "Ihr neues monatliches Hausgeld ab 01.01.2024 beträgt 110,00 EUR.")
    
    c.save()

if __name__ == "__main__":
    create_pdf()
