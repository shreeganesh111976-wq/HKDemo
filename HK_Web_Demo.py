import streamlit as st
import pandas as pd
import os
import time
import calendar
import json
import zipfile
import io
import urllib.parse
import smtplib
import ssl
import re
import sys
import base64
from email.message import EmailMessage
from datetime import datetime, date, timedelta
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
import altair as alt 

# --- TRY IMPORTING QR LIBRARIES ---
try:
    import qrcode
    from PIL import Image
except ImportError:
    st.error("⚠️ Missing libraries! Please run: pip install qrcode[pil]")
    st.stop()

# --- PAGE CONFIGURATION (MUST BE FIRST) ---
st.set_page_config(page_title="HisaabKeeper Cloud", layout="wide", page_icon="🧾")

# --- GLOBAL CONSTANTS & PATHS ---
APP_NAME = "HisaabKeeper"
HARD_STOP_DATE = date(2026, 6, 30) 

# Cloud/Linux Compatible Paths
BASE_PATH = os.getcwd()

# Data Folder Structure
DATA_FOLDER = os.path.join(BASE_PATH, "Hisaab_Data")
DEFAULT_BILL_FOLDER = os.path.join(BASE_PATH, "Hisaab_Generated_Bills")
LETTERHEAD_BILL_FOLDER = os.path.join(BASE_PATH, "Hisaab_Letterhead_Bills")

# File Paths
GST_FILE = os.path.join(DATA_FOLDER, "gst_data.xlsx")
INWARD_FILE = os.path.join(DATA_FOLDER, "inward_supply.xlsx")
CUSTOMER_FILE = os.path.join(DATA_FOLDER, "customers.xlsx")
RECEIPT_FILE = os.path.join(DATA_FOLDER, "receipts.xlsx")
PROFILE_FILE = os.path.join(DATA_FOLDER, "profile.json")
PASSWORD_FILE = os.path.join(DATA_FOLDER, "admin_pass.txt")
LICENSE_FILE = os.path.join(DATA_FOLDER, "license.json") 
LOGO_FILE = os.path.join(DATA_FOLDER, "company_logo.png")
SIGNATURE_FILE = os.path.join(DATA_FOLDER, "signature.png")
APP_LOGO_FILE = os.path.join(DATA_FOLDER, "app_logo.png")
QR_TEMP_FILE = os.path.join(DATA_FOLDER, "temp_qr.png")

# Constants
STATE_CODES = {
    '01': 'Jammu & Kashmir', '02': 'Himachal Pradesh', '03': 'Punjab', '04': 'Chandigarh', '05': 'Uttarakhand',
    '06': 'Haryana', '07': 'Delhi', '08': 'Rajasthan', '09': 'Uttar Pradesh', '10': 'Bihar', '11': 'Sikkim',
    '12': 'Arunachal Pradesh', '13': 'Nagaland', '14': 'Manipur', '15': 'Mizoram', '16': 'Tripura', '17': 'Meghalaya',
    '18': 'Assam', '19': 'West Bengal', '20': 'Jharkhand', '21': 'Odisha', '22': 'Chhattisgarh', '23': 'Madhya Pradesh',
    '24': 'Gujarat', '25': 'Daman & Diu', '26': 'Dadra & Nagar Haveli', '27': 'Maharashtra', '28': 'Andhra Pradesh',
    '29': 'Karnataka', '30': 'Goa', '31': 'Lakshadweep', '32': 'Kerala', '33': 'Tamil Nadu', '34': 'Puducherry',
    '35': 'Andaman & Nicobar Islands', '36': 'Telangana', '37': 'Andhra Pradesh (New)', '97': 'Other Territory'
}

# --- INITIALIZATION HELPER (PREVENTS CRASHES) ---
def init_app_files():
    """Checks for necessary folders and files. Creates them if missing."""
    os.makedirs(DATA_FOLDER, exist_ok=True)
    os.makedirs(DEFAULT_BILL_FOLDER, exist_ok=True)
    os.makedirs(LETTERHEAD_BILL_FOLDER, exist_ok=True)

    # Initialize Excel Files with Headers if they don't exist
    if not os.path.exists(GST_FILE):
        pd.DataFrame(columns=['Bill No.', 'Date', 'Buyer Name', 'GSTIN', 'Invoice Value', 'Received Amount', 'Status', 'Items']).to_excel(GST_FILE, index=False)
    
    if not os.path.exists(CUSTOMER_FILE):
        pd.DataFrame(columns=["Name", "GSTIN", "Address 1", "Address 2", "Address 3", "Mobile", "Email"]).to_excel(CUSTOMER_FILE, index=False)

    if not os.path.exists(RECEIPT_FILE):
        pd.DataFrame(columns=['Date', 'Party Name', 'Amount', 'Note']).to_excel(RECEIPT_FILE, index=False)
        
    if not os.path.exists(INWARD_FILE):
        pd.DataFrame(columns=['Date', 'Supplier Name', 'GSTIN', 'Invoice No', 'Taxable', 'CGST', 'SGST', 'IGST', 'Total Value']).to_excel(INWARD_FILE, index=False)

# Run Initialization
init_app_files()

# --- LICENSE SYSTEM (CLOUD COMPATIBLE) ---
def get_current_validity():
    default_date = date(2025, 12, 31)
    if os.path.exists(LICENSE_FILE):
        try:
            with open(LICENSE_FILE, 'r') as f:
                data = json.load(f)
                return datetime.strptime(data.get('valid_until', '2025-12-31'), "%Y-%m-%d").date()
        except:
            return default_date
    return default_date

def check_license_system():
    today = date.today()
    if today > HARD_STOP_DATE:
        st.error(f"🚫 Software License Expired Permanently on {HARD_STOP_DATE.strftime('%d-%m-%Y')}. Please contact administrator.")
        return False
    current_valid_until = get_current_validity()
    if today <= current_valid_until:
        return True 

    required_code = ""
    new_validity = ""
    
    # 2026 Extension Logic
    if date(2026, 1, 1) <= today <= date(2026, 1, 31):
        required_code = "JanNowUnLocked"; new_validity = "2026-01-31"
    elif date(2026, 2, 1) <= today <= date(2026, 2, 28):
        required_code = "MartobeUnLocked"; new_validity = "2026-02-28"
    elif date(2026, 3, 1) <= today <= date(2026, 3, 31):
        required_code = "itsEndingof202526"; new_validity = "2026-03-31"
    elif date(2026, 4, 1) <= today <= date(2026, 4, 30):
        required_code = "iTS_26-27_NEWfy"; new_validity = "2026-04-30"
    elif date(2026, 5, 1) <= today <= date(2026, 5, 31):
        required_code = "aPriLFoOlendeD"; new_validity = "2026-05-31"
    elif date(2026, 6, 1) <= today <= date(2026, 6, 30):
        required_code = "NowtimesFOR-hardstop"; new_validity = "2026-06-30"
    else:
        # Fallback for gap periods or errors
        st.warning("License check: Please contact support.")
        return False

    st.markdown("<br>", unsafe_allow_html=True)
    with st.container():
        st.error("🔒 Subscription Ended. Enter Activation Code.")
        activation_input = st.text_input("Enter Activation Code", type="password", key="act_code")
        
        if st.button("Unlock Software", type="primary", use_container_width=True):
            if activation_input == required_code:
                with open(LICENSE_FILE, 'w') as f:
                    json.dump({"valid_until": new_validity}, f)
                st.success(f"✅ Unlocked! Valid until {new_validity}")
                time.sleep(1.5)
                st.rerun()
            else:
                st.error("❌ Invalid Activation Code")
    return False

if not check_license_system():
    st.stop() 

# --- GENERIC HELPER FUNCTIONS ---
def load_profile():
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def check_admin_password(input_pass):
    if not os.path.exists(PASSWORD_FILE): return False
    with open(PASSWORD_FILE, 'r') as f:
        stored_pass = f.read().strip()
    return input_pass == stored_pass

def set_admin_password(new_pass):
    with open(PASSWORD_FILE, 'w') as f:
        f.write(new_pass)

def load_data(filepath, columns):
    if os.path.exists(filepath):
        try: 
            df = pd.read_excel(filepath)
            for col in columns:
                if col not in df.columns: df[col] = ""
            return df.fillna("")
        except: return pd.DataFrame(columns=columns)
    return pd.DataFrame(columns=columns)

def save_data(filepath, df):
    df.to_excel(filepath, index=False)

def get_save_directory(profile_data, is_letterhead=False):
    # Cloud environment: force use of local directories within the container
    if is_letterhead:
        return LETTERHEAD_BILL_FOLDER
    return DEFAULT_BILL_FOLDER

def find_invoice_pdf(bill_no):
    try:
        invoice_id = bill_no.replace("/", "_").replace("\\", "_")
        search_dirs = [DEFAULT_BILL_FOLDER, LETTERHEAD_BILL_FOLDER]
        for search_dir in search_dirs:
            for root, dirs, files in os.walk(search_dir):
                for file in files:
                    if file.endswith(".pdf") and invoice_id in file:
                        return os.path.join(root, file)
    except: return None
    return None

# --- QR & LINKS ---
def generate_upi_qr(upi_id, name, amount, note):
    if not upi_id: return None
    safe_note = urllib.parse.quote(note)
    safe_name = urllib.parse.quote(name)
    upi_url = f"upi://pay?pa={upi_id}&pn={safe_name}&am={amount}&tn={safe_note}&cu=INR"
    
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # Simple QR without Logo embedding to be safe on cloud/linux/mobile
    qr_img.save(QR_TEMP_FILE)
    return QR_TEMP_FILE

def get_whatsapp_deep_link(number, message):
    """Generates a deep link for Mobile/Web compatibility."""
    if not number: return None
    s_num = str(number).split('.')[0]
    clean_num = ''.join(filter(str.isdigit, s_num))
    if len(clean_num) == 10: clean_num = "91" + clean_num
    elif len(clean_num) < 10: return None
    
    encoded_msg = urllib.parse.quote(message)
    # Uses wa.me which works on both Mobile App and Web
    return f"https://wa.me/{clean_num}?text={encoded_msg}"

def get_invoice_email_body(cust_name, invoice_no, firm_name, date_str, amount, contact_info):
    return f"""
    <html><body>
    <p>Hi <b>{cust_name}</b>,</p>
    <p>Greetings from <b>{firm_name}</b>. I’m sending over the invoice <b>{invoice_no}</b> dated <b>{date_str}</b> for <b>₹{amount}</b>.</p>
    <br><p><b>{firm_name}</b><br>{contact_info}</p>
    </body></html>
    """

def get_invoice_whatsapp_msg(cust_name, invoice_no, firm_name, date_str, amount, contact_info):
    return f"""Hi *{cust_name}*,

Greetings from *{firm_name}*. Sending invoice *{invoice_no}* dated *{date_str}* for *₹{amount}*.

*{firm_name}*
{contact_info}"""

def get_ledger_whatsapp_msg(name, balance, firm_name, contact_info):
    return f"""Hi *{name}*,
Greetings from *{firm_name}*. Gentle reminder for pending payment: *₹ {balance:,.2f}*.
*{firm_name}*"""

# --- EMAIL ---
def send_invoice_email(pdf_path, to_email, cust_name, invoice_no, profile, total_amt):
    sender_email = profile.get('Sender Email', '')
    sender_pass = profile.get('App Password', '')
    if not sender_email or not sender_pass: return "⚠️ Setup Email/App Password in Profile."
    if not to_email or "@" not in to_email: return "⚠️ Invalid Customer Email."

    msg = EmailMessage()
    msg['Subject'] = f"Invoice {invoice_no} from {profile.get('Business Name','')}"
    msg['From'] = sender_email; msg['To'] = to_email
    
    html_content = get_invoice_email_body(cust_name, invoice_no, profile.get('Business Name',''), datetime.now().strftime("%d-%m-%Y"), f"{total_amt:,.2f}", profile.get('Mobile',''))
    msg.add_alternative(html_content, subtype='html')

    try:
        with open(pdf_path, 'rb') as f:
            file_data = f.read(); file_name = os.path.basename(pdf_path)
        msg.add_attachment(file_data, maintype='application', subtype='pdf', filename=file_name)
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
            smtp.login(sender_email, sender_pass); smtp.send_message(msg)
        return "✅ Email Sent Successfully!"
    except Exception as e: return f"❌ Email Failed: {e}"

def send_plain_email(to_email, subject, html_body, profile, attachment_path=None):
    sender_email = profile.get('Sender Email', '')
    sender_pass = profile.get('App Password', '')
    if not sender_email or not sender_pass: return "⚠️ Setup Email Profile first."
    
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender_email; msg['To'] = to_email
    msg.add_alternative(html_body, subtype='html')
    
    if attachment_path and os.path.exists(attachment_path):
        try:
            with open(attachment_path, 'rb') as f:
                img_data = f.read()
                msg.add_attachment(img_data, maintype='image', subtype='png', filename="Payment_QR.png")
        except: pass

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
            smtp.login(sender_email, sender_pass); smtp.send_message(msg)
        return "✅ Email Sent!"
    except Exception as e: return f"❌ Failed: {e}"

# --- PDF GENERATION LOGIC ---
def get_invoice_paths_dual(date_obj, invoice_no, party_name, profile_data):
    year = date_obj.year; month = date_obj.month
    if month < 4: fy = f"FY {year-1}-{str(year)[-2:]}"
    else: fy = f"FY {year}-{str(year+1)[-2:]}"
    month_name = date_obj.strftime("%B")
    
    # 1. Main Path
    base_dir_main = get_save_directory(profile_data, is_letterhead=False)
    save_path_main = os.path.join(base_dir_main, fy, f"{month_name} {year}")
    os.makedirs(save_path_main, exist_ok=True)
    
    # 2. Letterhead Path
    base_dir_lh = get_save_directory(profile_data, is_letterhead=True)
    save_path_lh = os.path.join(base_dir_lh, fy, f"{month_name} {year}")
    os.makedirs(save_path_lh, exist_ok=True)
    
    safe_inv = invoice_no.replace("/", "_").replace("\\", "_")
    safe_name = "".join(c for c in party_name if c.isalnum() or c in " ._").rstrip()
    filename = f"{safe_inv}_{safe_name}.pdf"
    
    return os.path.join(save_path_main, filename), os.path.join(save_path_lh, filename)

def draw_header_on_canvas(c, w, h, seller, buyer, inv_no, is_letterhead, theme, font_header, font_body):
    # --- HEADER SECTION ---
    if not is_letterhead:
        if theme == 'Formal':
            c.setLineWidth(3); c.rect(20, h-160, w-40, 140) 
            c.setLineWidth(1)

        if os.path.exists(LOGO_FILE):
            try:
                logo = ImageReader(LOGO_FILE)
                c.drawImage(logo, 30, h-100, width=2.0*inch, height=1.0*inch, mask='auto', preserveAspectRatio=True)
            except: pass

        center_x = (w / 2) + 20 
        c.setFont(font_header, 18)
        c.drawCentredString(center_x, h-50, seller.get('Business Name', 'Unknown Firm'))
        
        if seller.get('Tagline'):
            c.setFont(font_body, 10)
            c.drawCentredString(center_x, h-65, seller.get('Tagline'))

        c.setFont(font_body, 9)
        y_contact = h-80
        
        if seller.get('Is GST', 'No') == 'Yes':
            if seller.get('GSTIN'):
                c.drawCentredString(center_x, y_contact, f"GSTIN: {seller.get('GSTIN', '')}")
                y_contact -= 12
        else:
            if seller.get('PAN'):
                c.drawCentredString(center_x, y_contact, f"PAN: {seller.get('PAN', '')}")
                y_contact -= 12
        
        c.drawCentredString(center_x, y_contact, seller.get('Addr1', ''))
        c.drawCentredString(center_x, y_contact-12, seller.get('Addr2', ''))
        c.drawCentredString(center_x, y_contact-24, f"M: {seller.get('Mobile', '')} | E: {seller.get('Email', '')}")
    
    title_text = "TAX INVOICE" if seller.get('Is GST', 'No') == 'Yes' else "INVOICE"
    c.setFont(font_header, 14)
    c.drawCentredString(w/2, h-140, title_text)
    
    if theme != 'Modern' and not is_letterhead:
        c.line(30, h-145, w-30, h-145)
    
    # --- BILL TO SECTION ---
    y = h-170
    ship_data = buyer.get('Shipping', {})
    
    c.setFont(font_header, 10); c.drawString(40, y, "Bill To:")
    c.setFont(font_body, 10)
    c.drawString(40, y-15, buyer['Name'])
    
    if seller.get('Is GST', 'No') == 'Yes':
        c.drawString(40, y-30, f"GSTIN: {buyer.get('GSTIN', 'URP')}")
        addr_start_y = y-45
    else:
        addr_start_y = y-30

    c.drawString(40, addr_start_y, f"{buyer.get('Address 1', '')}")
    if buyer.get('Address 2'):
        addr_start_y -= 12
        c.drawString(40, addr_start_y, f"{buyer.get('Address 2', '')}")
    if buyer.get('Address 3'):
        addr_start_y -= 12
        c.drawString(40, addr_start_y, f"{buyer.get('Address 3', '')}")
    
    addr_start_y -= 12
    c.drawString(40, addr_start_y, f"M: {buyer.get('Mobile', '')}")

    if ship_data:
        x_ship = 250
        c.setFont(font_header, 10); c.drawString(x_ship, y, "Ship To:")
        c.setFont(font_body, 10)
        c.drawString(x_ship, y-15, ship_data.get('Name', ''))
        
        if seller.get('Is GST', 'No') == 'Yes':
            c.drawString(x_ship, y-30, f"GSTIN: {ship_data.get('GSTIN', '')}")
            s_addr_y = y-45
        else:
            s_addr_y = y-30
        
        c.drawString(x_ship, s_addr_y, f"{ship_data.get('Addr1', '')}")
        if ship_data.get('Addr2'):
            s_addr_y -= 12
            c.drawString(x_ship, s_addr_y, f"{ship_data.get('Addr2', '')}")

    # Invoice Details 
    x_inv = 400
    c.setFont(font_header, 10); c.drawString(x_inv, y, "Invoice Details:")
    c.setFont(font_body, 10)
    c.drawString(x_inv, y-15, f"Inv No: {inv_no}")
    c.drawString(x_inv, y-30, f"Date: {buyer['Date']}")
    if seller.get('Is GST', 'No') == 'Yes':
        pos_code = buyer.get('POS Code', '24')
        c.drawString(x_inv, y-45, f"POS: {pos_code}-{STATE_CODES.get(pos_code, '')}")

    return h - 280 

def draw_footer_on_canvas(c, w, h, seller, font_header, font_body):
    foot_y = 130 
    c.line(30, foot_y + 90, w-30, foot_y + 90)
    
    c.setFont(font_header, 10); c.drawString(40, foot_y+75, "Bank Details:")
    c.setFont(font_body, 9)
    c.drawString(40, foot_y+60, f"Bank: {seller.get('Bank Name','')}")
    c.drawString(40, foot_y+48, f"A/c: {seller.get('Account No','')}")
    c.drawString(40, foot_y+36, f"IFSC: {seller.get('IFSC','')}")
    
    sign_y = foot_y + 50 
    c.drawRightString(w-40, sign_y, f"For, {seller.get('Business Name', '')}")
    
    if os.path.exists(SIGNATURE_FILE):
        try:
            sig_img = ImageReader(SIGNATURE_FILE)
            c.drawImage(sig_img, w-160, sign_y-55, width=1.4*inch, height=0.7*inch, mask='auto', preserveAspectRatio=True)
        except: pass

    c.drawRightString(w-40, sign_y-60, "Authorized Signatory")
    
    c.setFillColor(colors.grey)
    c.setFont(font_body, 7)
    footer_msg = "Generated using HisaabKeeper"
    c.drawCentredString(w/2, 15, footer_msg)
    c.setFillColor(colors.black)

def generate_pdf(seller, buyer, items, inv_no, path, totals, is_letterhead=False):
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4 
    theme = seller.get('Theme', 'Existing')
    
    if theme == 'Modern': 
        font_header = "Helvetica-Bold"; font_body = "Helvetica"
        accent_color = HexColor('#2C3E50'); text_color_head = colors.white; grid_color = colors.lightgrey
    else: 
        font_header = "Helvetica-Bold"; font_body = "Helvetica"
        accent_color = colors.grey; text_color_head = colors.whitesmoke; grid_color = colors.black

    is_gst_bill = seller.get('Is GST', 'No') == 'Yes'
    if is_gst_bill:
        header = ["Sr.\nNo.", "Description", "HSN", "Qty", "UOM", "Rate", "Amount"]
        col_widths = [0.5*inch, 2.6*inch, 1.0*inch, 0.8*inch, 0.6*inch, 1.0*inch, 1.2*inch]
        span_cols = 5
    else:
        header = ["Sr.\nNo.", "Description", "Qty", "UOM", "Rate", "Amount"]
        col_widths = [0.5*inch, 3.6*inch, 0.8*inch, 0.6*inch, 1.0*inch, 1.2*inch]
        span_cols = 4

    data = [header]
    for i, item in enumerate(items, 1):
        amt = item['Qty'] * item['Rate']
        desc = str(item['Description']).replace('\n', ' ') 
        
        if is_gst_bill:
            data.append([str(i), desc, str(item.get('HSN', '')), f"{item['Qty']:.2f}", str(item.get('UOM', '')), f"{item['Rate']:.2f}", f"{amt:.2f}"])
        else:
            data.append([str(i), desc, f"{item['Qty']:.2f}", str(item.get('UOM', '')), f"{item['Rate']:.2f}", f"{amt:.2f}"])
    
    summary_start = len(data)
    if is_gst_bill:
        data.append(['Taxable Value', '', '', '', '', '', f"{totals['taxable']:.2f}"])
        if totals['is_intra']:
            data.append(['Add: CGST', '', '', '', '', '', f"{totals['cgst']:.2f}"])
            data.append(['Add: SGST', '', '', '', '', '', f"{totals['sgst']:.2f}"])
        else:
            data.append(['Add: IGST', '', '', '', '', '', f"{totals['igst']:.2f}"])
    
    data.append(['Grand Total', '', '', '', '', '', f"{totals['total']:.2f}"])
    
    style_cmds = [
        ('FONTNAME', (0,0), (-1,-1), font_body),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,1), (1, summary_start-1), 'LEFT'),
        ('ALIGN', (0, summary_start), (-2,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, grid_color)
    ]
    
    for i in range(summary_start, len(data)): 
        style_cmds.append(('SPAN', (0,i), (span_cols,i)))
    
    main_table = Table(data, colWidths=col_widths)
    main_table.setStyle(TableStyle(style_cmds))

    # Pages Calculation
    header_bottom_y = h - 280 
    footer_height = 230 
    usable_height = header_bottom_y - footer_height
    
    table_parts = []
    current_data = main_table
    while True:
        w_t, h_t = current_data.wrap(w, h)
        if h_t <= usable_height:
            table_parts.append(current_data); break
        else:
            result = current_data.split(w, usable_height)
            if len(result) == 2:
                table_parts.append(result[0]); current_data = result[1]
            else:
                table_parts.append(current_data); break

    total_pages = len(table_parts)

    for page_idx, part in enumerate(table_parts):
        y_start = draw_header_on_canvas(c, w, h, seller, buyer, inv_no, is_letterhead, theme, font_header, font_body)
        pw, ph = part.wrapOn(c, w, h)
        part.drawOn(c, 30, y_start - ph)
        draw_footer_on_canvas(c, w, h, seller, font_header, font_body)
        c.setFont(font_body, 8)
        c.drawCentredString(w/2, 25, f"Page {page_idx+1} of {total_pages}") 
        c.showPage()
    
    c.save()

# --- CSS STYLING FOR MOBILE ---
st.markdown("""
    <style>
    /* Make buttons easy to tap */
    div.stButton > button { min-height: 45px; font-weight: bold; }
    /* Hide default menu */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    /* Better table scrollers on mobile */
    div[data-testid="stDataFrame"] { overflow-x: auto; }
    </style>
""", unsafe_allow_html=True)

# --- APP LOGIC ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "nav_index" not in st.session_state: st.session_state.nav_index = 0
if "edit_invoice_data" not in st.session_state: st.session_state.edit_invoice_data = None
if "last_invoice_details" not in st.session_state: st.session_state.last_invoice_details = None
if "billing_key" not in st.session_state: st.session_state.billing_key = 0

def check_password():
    if st.session_state.password_input == "Dhruv@63":
        st.session_state.authenticated = True
    else: st.error("❌ Incorrect Password")

if not st.session_state.authenticated:
    st.markdown("<br><br><h1 style='text-align: center;'>HisaabKeeper Cloud</h1>", unsafe_allow_html=True)
    st.text_input("Password", type="password", key="password_input", on_change=check_password)
    st.button("Login", on_click=check_password, use_container_width=True)
    st.stop()

# --- MAIN APP ---
profile = load_profile()
firm_name = profile.get('Business Name', 'My Firm Name')
menu_options = ["📊 Dashboard", "👥 Customer Master", "📒 Customer Ledger", "🧾 Billing Master", "🚚 Inward Supply", "📂 Record Master", "⚙️ Company Profile"]

with st.sidebar:
    st.markdown(f"## {firm_name}")
    st.markdown("---")
    selection = st.radio("Navigate", menu_options, index=st.session_state.nav_index)
    if selection != menu_options[st.session_state.nav_index]:
        st.session_state.nav_index = menu_options.index(selection)
        st.rerun()
    st.markdown("---")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False; st.rerun()

# ---------------------------------------------------------
# 1. PROFILE SECTION
# ---------------------------------------------------------
if "Company Profile" in selection:
    st.header("⚙️ Company Profile")
    with st.expander("📝 Edit Profile Details", expanded=True):
        with st.form("prof_form"):
            bn = st.text_input("Business Name", profile.get('Business Name',''))
            tag = st.text_input("Tagline", profile.get('Tagline',''))
            
            c1, c2 = st.columns(2)
            with c1: is_gst = st.selectbox("Registered GST?", ["Yes", "No"], index=0 if profile.get('Is GST', 'No') == 'Yes' else 1)
            with c2: gst_val = st.text_input("GSTIN", profile.get('GSTIN',''))
            
            st.markdown("---")
            mob = st.text_input("Mobile", profile.get('Mobile',''))
            em = st.text_input("Email", profile.get('Email',''))
            addr1 = st.text_input("Address 1", profile.get('Addr1',''))
            addr2 = st.text_input("Address 2", profile.get('Addr2',''))
            
            st.markdown("---")
            bank = st.text_input("Bank Name", profile.get('Bank Name',''))
            acc = st.text_input("Account No", profile.get('Account No',''))
            ifsc = st.text_input("IFSC", profile.get('IFSC',''))
            upi = st.text_input("UPI ID (for QRs)", profile.get('UPI ID',''))

            # Email Settings
            st.markdown("---")
            s_email = st.text_input("Sender Email (Gmail)", profile.get('Sender Email',''))
            s_pass = st.text_input("App Password", profile.get('App Password',''), type="password")

            if st.form_submit_button("💾 Save Profile", type="primary"):
                data = {
                    "Business Name": bn, "Tagline": tag, "Is GST": is_gst, "GSTIN": gst_val,
                    "Mobile": mob, "Email": em, "Addr1": addr1, "Addr2": addr2,
                    "Bank Name": bank, "Account No": acc, "IFSC": ifsc, "UPI ID": upi,
                    "Sender Email": s_email, "App Password": s_pass
                }
                with open(PROFILE_FILE, 'w') as f: json.dump(data, f)
                st.success("Profile Saved!")
                time.sleep(1); st.rerun()

# ---------------------------------------------------------
# 2. DASHBOARD
# ---------------------------------------------------------
elif "Dashboard" in selection:
    st.header(f"📊 {firm_name}")
    st.markdown("---")
    
    b2b = load_data(GST_FILE, ['Date', 'Invoice Value', 'Taxable'])
    inward = load_data(INWARD_FILE, ['Date', 'Total Value', 'Taxable'])
    b2b['Invoice Value'] = pd.to_numeric(b2b['Invoice Value'], errors='coerce')
    inward['Total Value'] = pd.to_numeric(inward['Total Value'], errors='coerce')

    total_sales = b2b['Invoice Value'].sum()
    total_purch = inward['Total Value'].sum()

    # Mobile Friendly Grid
    c1, c2 = st.columns(2)
    with c1: st.metric("Total Sales", f"₹ {total_sales:,.0f}")
    with c2: st.metric("Total Purchase", f"₹ {total_purch:,.0f}")
    
    st.markdown("### 📉 Quick Analysis")
    chart_data = pd.DataFrame({'Type': ['Sales', 'Purchase'], 'Amount': [total_sales, total_purch]})
    c = alt.Chart(chart_data).mark_bar().encode(x='Type', y='Amount', color='Type')
    st.altair_chart(c, use_container_width=True)

# ---------------------------------------------------------
# 3. CUSTOMER MASTER
# ---------------------------------------------------------
elif "Customer Master" in selection:
    st.header("👥 Customer Master")
    cust_df = load_data(CUSTOMER_FILE, ["Name", "GSTIN", "Mobile"])
    
    with st.expander("➕ Add New Customer", expanded=False):
        with st.form("add_cust"):
            name = st.text_input("Name")
            gst = st.text_input("GSTIN")
            mob = st.text_input("Mobile")
            email = st.text_input("Email")
            a1 = st.text_input("Address 1")
            a2 = st.text_input("Address 2")
            
            if st.form_submit_button("Save Customer", type="primary"):
                new_row = {"Name": name, "GSTIN": gst, "Mobile": mob, "Email": email, "Address 1": a1, "Address 2": a2}
                cust_df = pd.concat([cust_df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(CUSTOMER_FILE, cust_df)
                st.success("Added!")
                st.rerun()
    
    st.dataframe(cust_df, use_container_width=True)

# ---------------------------------------------------------
# 4. BILLING MASTER
# ---------------------------------------------------------
elif "Billing Master" in selection:
    st.header("🧾 New Invoice")
    
    cust_df = load_data(CUSTOMER_FILE, ["Name", "GSTIN", "Address 1", "Address 2", "Mobile", "Email"])
    cust_names = ["Select"] + cust_df['Name'].tolist()
    
    # Selection Wrapper
    c1, c2 = st.columns([2, 1])
    with c1:
        sel_name = st.selectbox("Customer", cust_names)
    with c2:
        inv_date = st.date_input("Date", date.today())
        
    inv_no = st.text_input("Invoice No", placeholder="Ex: FY25-26/001")
    
    # Prepare Items
    if "bill_items" not in st.session_state:
        st.session_state.bill_items = pd.DataFrame([{"Description": "", "Qty": 1.0, "Rate": 0.0}])

    st.subheader("Items")
    edited_items = st.data_editor(st.session_state.bill_items, num_rows="dynamic", use_container_width=True, key="bill_editor")
    
    # Calculate
    valid_items = edited_items[edited_items['Description'] != ""].copy()
    valid_items['Amount'] = valid_items['Qty'] * valid_items['Rate']
    subtotal = valid_items['Amount'].sum()
    
    st.markdown(f"### Subtotal: ₹ {subtotal:,.2f}")
    
    if st.button("🚀 Generate Invoice", type="primary", use_container_width=True):
        if sel_name == "Select" or not inv_no:
            st.error("Select Customer and Enter Invoice No")
        else:
            cust_data = cust_df[cust_df['Name'] == sel_name].iloc[0].to_dict()
            cust_data['Date'] = inv_date.strftime("%d-%m-%Y")
            
            # Simple tax logic (assume 18% for demo or 0 if not GST)
            is_gst = profile.get('Is GST', 'No') == 'Yes'
            tax_amt = subtotal * 0.18 if is_gst else 0
            total = subtotal + tax_amt
            
            totals = {'taxable': subtotal, 'cgst': tax_amt/2, 'sgst': tax_amt/2, 'igst': 0, 'total': total, 'is_intra': True}
            
            # Generate PDF
            path_main, path_lh = get_invoice_paths_dual(inv_date, inv_no, sel_name, profile)
            generate_pdf(profile, cust_data, valid_items.to_dict('records'), inv_no, path_main, totals, is_letterhead=False)
            
            # Save Record
            gst_df = load_data(GST_FILE, [])
            new_rec = {'Bill No.': inv_no, 'Date': cust_data['Date'], 'Buyer Name': sel_name, 'Invoice Value': total, 'Items': json.dumps(valid_items.to_dict('records'))}
            save_data(GST_FILE, pd.concat([gst_df, pd.DataFrame([new_rec])], ignore_index=True))
            
            # Success State
            st.session_state.last_invoice_details = {'path': path_main, 'total': total, 'cust': sel_name, 'mobile': cust_data['Mobile'], 'inv': inv_no}
            st.rerun()

    # Success Actions
    if st.session_state.last_invoice_details:
        det = st.session_state.last_invoice_details
        st.success(f"Generated {det['inv']} for ₹ {det['total']:,.2f}")
        
        c_down, c_wa = st.columns(2)
        with c_down:
            with open(det['path'], "rb") as f:
                st.download_button("⬇️ Download PDF", f, file_name=os.path.basename(det['path']), mime="application/pdf", type="primary", use_container_width=True)
        
        with c_wa:
            msg = get_invoice_whatsapp_msg(det['cust'], det['inv'], firm_name, date.today().strftime("%d-%m-%Y"), det['total'], profile.get('Mobile',''))
            wa_link = get_whatsapp_deep_link(det['mobile'], msg)
            if wa_link:
                st.link_button("📱 Send on WhatsApp", wa_link, type="secondary", use_container_width=True)
            else:
                st.warning("No Mobile Number")

# ---------------------------------------------------------
# 5. CUSTOMER LEDGER
# ---------------------------------------------------------
elif "Customer Ledger" in selection:
    st.header("📒 Customer Ledger")
    cust_df = load_data(CUSTOMER_FILE, ["Name", "Mobile"])
    all_cust = ["Select"] + cust_df['Name'].tolist()
    
    sel_cust = st.selectbox("Select Customer", all_cust)
    
    if sel_cust != "Select":
        inv = load_data(GST_FILE, ['Buyer Name', 'Invoice Value', 'Bill No.', 'Date'])
        rec = load_data(RECEIPT_FILE, ['Party Name', 'Amount', 'Date'])
        
        c_inv = inv[inv['Buyer Name'] == sel_cust]
        c_rec = rec[rec['Party Name'] == sel_cust]
        
        total_inv = pd.to_numeric(c_inv['Invoice Value'], errors='coerce').sum()
        total_rec = pd.to_numeric(c_rec['Amount'], errors='coerce').sum()
        balance = total_inv - total_rec
        
        st.info(f"💰 Pending Balance: ₹ {balance:,.2f}")
        
        with st.expander("➕ Add Receipt", expanded=True):
            with st.form("rec_form"):
                r_amt = st.number_input("Amount", min_value=0.0)
                r_note = st.text_input("Note")
                if st.form_submit_button("Save Receipt", type="primary"):
                    new_r = {'Date': date.today().strftime("%d-%m-%Y"), 'Party Name': sel_cust, 'Amount': r_amt, 'Note': r_note}
                    save_data(RECEIPT_FILE, pd.concat([load_data(RECEIPT_FILE, []), pd.DataFrame([new_r])], ignore_index=True))
                    st.success("Saved!"); time.sleep(1); st.rerun()

        # Payment Reminder
        if balance > 0:
            mob = cust_df[cust_df['Name'] == sel_cust].iloc[0]['Mobile']
            wa_msg = get_ledger_whatsapp_msg(sel_cust, balance, firm_name, profile.get('Mobile',''))
            wa_link = get_whatsapp_deep_link(mob, wa_msg)
            if wa_link:
                st.link_button("🔔 Send Reminder (WhatsApp)", wa_link, use_container_width=True)

# ---------------------------------------------------------
# 6. RECORDS & INWARD
# ---------------------------------------------------------
elif "Record Master" in selection:
    st.header("📂 Records")
    df = load_data(GST_FILE, ['Bill No.', 'Date', 'Buyer Name', 'Invoice Value'])
    st.dataframe(df, use_container_width=True)
    st.download_button("📥 Export CSV", df.to_csv(index=False).encode('utf-8'), "sales.csv", "text/csv")

elif "Inward Supply" in selection:
    st.header("🚚 Inward Supply")
    df = load_data(INWARD_FILE, ['Date', 'Supplier Name', 'Total Value'])
    
    with st.expander("➕ Add Purchase"):
        with st.form("inward_form"):
            sup = st.text_input("Supplier")
            val = st.number_input("Total Value")
            if st.form_submit_button("Save"):
                new_row = {'Date': date.today().strftime("%d-%m-%Y"), 'Supplier Name': sup, 'Total Value': val}
                save_data(INWARD_FILE, pd.concat([df, pd.DataFrame([new_row])], ignore_index=True))
                st.rerun()
    st.dataframe(df, use_container_width=True)