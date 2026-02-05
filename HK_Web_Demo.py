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

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="HisaabKeeper Cloud", layout="wide", page_icon="🧾")

# --- GLOBAL CONSTANTS ---
APP_NAME = "HisaabKeeper"
HARD_STOP_DATE = date(2026, 6, 30) 
# Original Base64 Logo (Placeholder for HK Logo)
HISAABKEEPER_LOGO_DATA = "" 

# --- PATHS (Cloud Compatible) ---
BASE_PATH = os.getcwd()

DATA_FOLDER = os.path.join(BASE_PATH, "Hisaab_Data")
DEFAULT_BILL_FOLDER = os.path.join(BASE_PATH, "Hisaab_Generated_Bills")
LETTERHEAD_BILL_FOLDER = os.path.join(BASE_PATH, "Hisaab_Letterhead_Bills")

GST_FILE = os.path.join(DATA_FOLDER, "gst_data.xlsx")
INWARD_FILE = os.path.join(DATA_FOLDER, "inward_supply.xlsx")
CUSTOMER_FILE = os.path.join(DATA_FOLDER, "customers.xlsx")
RECEIPT_FILE = os.path.join(DATA_FOLDER, "receipts.xlsx")
PROFILE_FILE = os.path.join(DATA_FOLDER, "profile.json")
PASSWORD_FILE = os.path.join(DATA_FOLDER, "admin_pass.txt")
LICENSE_FILE = os.path.join(DATA_FOLDER, "license.json") 
LOGO_FILE = os.path.join(DATA_FOLDER, "company_logo.png")
SIGNATURE_FILE = os.path.join(DATA_FOLDER, "signature.png")
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

# --- INITIALIZATION ---
def init_app_files():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    os.makedirs(DEFAULT_BILL_FOLDER, exist_ok=True)
    os.makedirs(LETTERHEAD_BILL_FOLDER, exist_ok=True)

    if not os.path.exists(GST_FILE):
        pd.DataFrame(columns=['Bill No.', 'Date', 'Buyer Name', 'GSTIN', 'Invoice Value', 'Taxable', 'CGST', 'SGST', 'IGST', 'Received Amount', 'Status', 'Items']).to_excel(GST_FILE, index=False)
    
    if not os.path.exists(CUSTOMER_FILE):
        pd.DataFrame(columns=["Name", "GSTIN", "Address 1", "Address 2", "Address 3", "Mobile", "Email"]).to_excel(CUSTOMER_FILE, index=False)

    if not os.path.exists(RECEIPT_FILE):
        pd.DataFrame(columns=['Date', 'Party Name', 'Amount', 'Note']).to_excel(RECEIPT_FILE, index=False)
        
    if not os.path.exists(INWARD_FILE):
        pd.DataFrame(columns=['Date', 'Supplier Name', 'GSTIN', 'Invoice No', 'Taxable', 'CGST', 'SGST', 'IGST', 'Total Value']).to_excel(INWARD_FILE, index=False)

init_app_files()

# --- HELPER FUNCTIONS ---
def load_profile():
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

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
    if is_letterhead: return LETTERHEAD_BILL_FOLDER
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

# --- QR CODE GENERATION (WITH LOGO SUPPORT) ---
def generate_upi_qr(upi_id, name, amount, note):
    if not upi_id: return None
    
    safe_note = urllib.parse.quote(note)
    safe_name = urllib.parse.quote(name)
    upi_url = f"upi://pay?pa={upi_id}&pn={safe_name}&am={amount}&tn={safe_note}&cu=INR"
    
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # Embed Logo Logic
    if HISAABKEEPER_LOGO_DATA:
        try:
            img_bytes = base64.b64decode(HISAABKEEPER_LOGO_DATA)
            logo = Image.open(io.BytesIO(img_bytes))
            qr_width, qr_height = qr_img.size
            logo_size = int(qr_width / 4)
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
            qr_img.paste(logo, pos)
        except: pass

    qr_img.save(QR_TEMP_FILE)
    return QR_TEMP_FILE

# --- PDF GENERATION LOGIC (RESTORED HSN TABLE) ---
def get_invoice_paths_dual(date_obj, invoice_no, party_name, profile_data):
    year = date_obj.year; month = date_obj.month
    if month < 4: fy = f"FY {year-1}-{str(year)[-2:]}"
    else: fy = f"FY {year}-{str(year+1)[-2:]}"
    month_name = date_obj.strftime("%B")
    
    base_dir_main = get_save_directory(profile_data, is_letterhead=False)
    save_path_main = os.path.join(base_dir_main, fy, f"{month_name} {year}")
    os.makedirs(save_path_main, exist_ok=True)
    
    base_dir_lh = get_save_directory(profile_data, is_letterhead=True)
    save_path_lh = os.path.join(base_dir_lh, fy, f"{month_name} {year}")
    os.makedirs(save_path_lh, exist_ok=True)
    
    safe_inv = invoice_no.replace("/", "_").replace("\\", "_")
    safe_name = "".join(c for c in party_name if c.isalnum() or c in " ._").rstrip()
    filename = f"{safe_inv}_{safe_name}.pdf"
    
    return os.path.join(save_path_main, filename), os.path.join(save_path_lh, filename)

def draw_header_on_canvas(c, w, h, seller, buyer, inv_no, is_letterhead, theme, font_header, font_body):
    if not is_letterhead:
        if theme == 'Formal':
            c.setLineWidth(3); c.rect(20, h-160, w-40, 140); c.setLineWidth(1)

        if os.path.exists(LOGO_FILE):
            try:
                logo = ImageReader(LOGO_FILE)
                c.drawImage(logo, 30, h-100, width=2.0*inch, height=1.0*inch, mask='auto', preserveAspectRatio=True)
            except: pass

        center_x = (w / 2) + 20 
        c.setFont(font_header, 18)
        c.drawCentredString(center_x, h-50, seller.get('Business Name', 'Unknown Firm'))
        
        if seller.get('Tagline'):
            c.setFont(font_body, 10); c.drawCentredString(center_x, h-65, seller.get('Tagline'))

        c.setFont(font_body, 9); y_contact = h-80
        if seller.get('Is GST', 'No') == 'Yes' and seller.get('GSTIN'):
            c.drawCentredString(center_x, y_contact, f"GSTIN: {seller.get('GSTIN', '')}"); y_contact -= 12
        elif seller.get('PAN'):
             c.drawCentredString(center_x, y_contact, f"PAN: {seller.get('PAN', '')}"); y_contact -= 12
        
        c.drawCentredString(center_x, y_contact, seller.get('Addr1', ''))
        c.drawCentredString(center_x, y_contact-12, seller.get('Addr2', ''))
        c.drawCentredString(center_x, y_contact-24, f"M: {seller.get('Mobile', '')} | E: {seller.get('Email', '')}")
    
    title_text = "TAX INVOICE" if seller.get('Is GST', 'No') == 'Yes' else "INVOICE"
    c.setFont(font_header, 14); c.drawCentredString(w/2, h-140, title_text)
    
    if theme != 'Modern' and not is_letterhead: c.line(30, h-145, w-30, h-145)
    
    y = h-170
    ship_data = buyer.get('Shipping', {})
    
    c.setFont(font_header, 10); c.drawString(40, y, "Bill To:")
    c.setFont(font_body, 10); c.drawString(40, y-15, buyer['Name'])
    
    if seller.get('Is GST', 'No') == 'Yes':
        c.drawString(40, y-30, f"GSTIN: {buyer.get('GSTIN', 'URP')}"); addr_start_y = y-45
    else: addr_start_y = y-30

    c.drawString(40, addr_start_y, f"{buyer.get('Address 1', '')}")
    if buyer.get('Address 2'): addr_start_y -= 12; c.drawString(40, addr_start_y, f"{buyer.get('Address 2', '')}")
    if buyer.get('Address 3'): addr_start_y -= 12; c.drawString(40, addr_start_y, f"{buyer.get('Address 3', '')}")
    
    if ship_data:
        x_ship = 250
        c.setFont(font_header, 10); c.drawString(x_ship, y, "Ship To:")
        c.setFont(font_body, 10); c.drawString(x_ship, y-15, ship_data.get('Name', ''))
        if seller.get('Is GST', 'No') == 'Yes':
            c.drawString(x_ship, y-30, f"GSTIN: {ship_data.get('GSTIN', '')}"); s_addr_y = y-45
        else: s_addr_y = y-30
        c.drawString(x_ship, s_addr_y, f"{ship_data.get('Addr1', '')}")
        if ship_data.get('Addr2'): s_addr_y -= 12; c.drawString(x_ship, s_addr_y, f"{ship_data.get('Addr2', '')}")

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
    
    c.setFillColor(colors.grey); c.setFont(font_body, 7)
    c.drawCentredString(w/2, 15, "Generated using HisaabKeeper")
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
        ('FONTNAME', (0,0), (-1,-1), font_body), ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,1), (1, summary_start-1), 'LEFT'), ('ALIGN', (0, summary_start), (-2,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, grid_color)
    ]
    for i in range(summary_start, len(data)): style_cmds.append(('SPAN', (0,i), (span_cols,i)))
    
    main_table = Table(data, colWidths=col_widths)
    main_table.setStyle(TableStyle(style_cmds))

    # --- HSN TABLE GENERATION ---
    hsn_table = None
    if is_gst_bill:
        tax_summary = {}
        for item in items:
            hsn_code = str(item.get('HSN', ''))
            gst_rate = float(item.get('GST', 0))
            taxable_val = float(item['Qty']) * float(item['Rate'])
            key = (hsn_code, gst_rate)
            if key not in tax_summary: tax_summary[key] = {'taxable': 0.0, 'cgst': 0.0, 'sgst': 0.0, 'igst': 0.0, 'total': 0.0}
            tax_summary[key]['taxable'] += taxable_val
            
            if totals['is_intra']:
                c_val = taxable_val * (gst_rate / 2 / 100); s_val = taxable_val * (gst_rate / 2 / 100); i_val = 0
            else:
                c_val = 0; s_val = 0; i_val = taxable_val * (gst_rate / 100)
            
            tax_summary[key]['cgst'] += c_val; tax_summary[key]['sgst'] += s_val; tax_summary[key]['igst'] += i_val
            tax_summary[key]['total'] += (taxable_val + c_val + s_val + i_val)
        
        hsn_data = [['HSN/SAC', 'Rate', 'Taxable', 'CGST', 'SGST', 'IGST', 'Total']]
        t_taxable = 0; t_grand = 0; t_cgst=0; t_sgst=0; t_igst=0
        for key in sorted(tax_summary.keys(), key=lambda x: x[0]):
            vals = tax_summary[key]
            hsn_data.append([str(key[0]), f"{key[1]}%", f"{vals['taxable']:.2f}", f"{vals['cgst']:.2f}", f"{vals['sgst']:.2f}", f"{vals['igst']:.2f}", f"{vals['total']:.2f}"])
            t_taxable += vals['taxable']; t_grand += vals['total']; t_cgst += vals['cgst']; t_sgst += vals['sgst']; t_igst += vals['igst']
        hsn_data.append(['Total', '', f"{t_taxable:.2f}", f"{t_cgst:.2f}", f"{t_sgst:.2f}", f"{t_igst:.2f}", f"{t_grand:.2f}"])
        
        hsn_table = Table(hsn_data, colWidths=[1.2*inch, 0.8*inch, 1.2*inch, 1.0*inch, 1.0*inch, 1.0*inch, 1.2*inch])
        hsn_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), font_body), ('FONTSIZE', (0,0), (-1,-1), 8), ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
            ('FONTNAME', (0,0), (-1,0), font_header), ('FONTNAME', (0, -1), (-1, -1), font_header)
        ]))

    # Pages Calculation
    header_bottom_y = h - 280; footer_height = 230; usable_height = header_bottom_y - footer_height
    table_parts = []; current_data = main_table
    while True:
        w_t, h_t = current_data.wrap(w, h)
        if h_t <= usable_height: table_parts.append(current_data); break
        else:
            result = current_data.split(w, usable_height)
            if len(result) == 2: table_parts.append(result[0]); current_data = result[1]
            else: table_parts.append(current_data); break

    total_pages = len(table_parts)
    hsn_needs_new_page = False
    if hsn_table:
        htw, hth = hsn_table.wrapOn(c, w, h)
        last_part_h = table_parts[-1].wrapOn(c, w, h)[1]
        space_left = usable_height - last_part_h - 20
        if space_left < hth: total_pages += 1; hsn_needs_new_page = True

    for page_idx, part in enumerate(table_parts):
        y_start = draw_header_on_canvas(c, w, h, seller, buyer, inv_no, is_letterhead, theme, font_header, font_body)
        pw, ph = part.wrapOn(c, w, h)
        part.drawOn(c, 30, y_start - ph)
        current_y = y_start - ph - 20
        draw_footer_on_canvas(c, w, h, seller, font_header, font_body)
        c.setFont(font_body, 8); c.drawCentredString(w/2, 25, f"Page {page_idx+1} of {total_pages}") 
        
        # Draw HSN
        if page_idx == len(table_parts) - 1:
            if hsn_table:
                if not hsn_needs_new_page: hsn_table.drawOn(c, 30, current_y - hth)
                else:
                    c.showPage()
                    y_start_new = draw_header_on_canvas(c, w, h, seller, buyer, inv_no, is_letterhead, theme, font_header, font_body)
                    draw_footer_on_canvas(c, w, h, seller, font_header, font_body)
                    c.drawCentredString(w/2, 25, f"Page {total_pages} of {total_pages}")
                    hsn_table.drawOn(c, 30, y_start_new - hth)
        c.showPage()
    c.save()

# --- CSS ---
st.markdown("""
    <style>
    div.stButton > button { min-height: 45px; font-weight: bold; }
    div[data-testid="stMetricValue"] { font-size: 1.5rem; }
    </style>
""", unsafe_allow_html=True)

# --- APP LOGIC ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "nav_index" not in st.session_state: st.session_state.nav_index = 0
if "edit_invoice_data" not in st.session_state: st.session_state.edit_invoice_data = None
if "last_invoice_details" not in st.session_state: st.session_state.last_invoice_details = None
if "billing_key" not in st.session_state: st.session_state.billing_key = 0

def check_password():
    if st.session_state.password_input == "Dhruv@63": st.session_state.authenticated = True
    else: st.error("❌ Incorrect Password")

if not st.session_state.authenticated:
    st.markdown("<br><br><h1 style='text-align: center;'>HisaabKeeper Cloud</h1>", unsafe_allow_html=True)
    st.text_input("Password", type="password", key="password_input", on_change=check_password)
    st.button("Login", on_click=check_password, use_container_width=True)
    st.stop()

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
    with st.expander("📝 Edit Profile", expanded=True):
        with st.form("prof_form"):
            bn = st.text_input("Business Name", profile.get('Business Name',''))
            tag = st.text_input("Tagline", profile.get('Tagline',''))
            c1, c2 = st.columns(2)
            with c1: is_gst = st.selectbox("Registered GST?", ["Yes", "No"], index=0 if profile.get('Is GST', 'No') == 'Yes' else 1)
            with c2: gst_val = st.text_input("GSTIN", profile.get('GSTIN',''))
            mob = st.text_input("Mobile", profile.get('Mobile',''))
            em = st.text_input("Email", profile.get('Email',''))
            addr1 = st.text_input("Address 1", profile.get('Addr1',''))
            addr2 = st.text_input("Address 2", profile.get('Addr2',''))
            bank = st.text_input("Bank Name", profile.get('Bank Name',''))
            acc = st.text_input("Account No", profile.get('Account No',''))
            ifsc = st.text_input("IFSC", profile.get('IFSC',''))
            upi = st.text_input("UPI ID", profile.get('UPI ID',''))
            s_email = st.text_input("Sender Email", profile.get('Sender Email',''))
            s_pass = st.text_input("App Password", profile.get('App Password',''), type="password")

            if st.form_submit_button("💾 Save Profile", type="primary"):
                data = {"Business Name": bn, "Tagline": tag, "Is GST": is_gst, "GSTIN": gst_val, "Mobile": mob, "Email": em, "Addr1": addr1, "Addr2": addr2, "Bank Name": bank, "Account No": acc, "IFSC": ifsc, "UPI ID": upi, "Sender Email": s_email, "App Password": s_pass}
                with open(PROFILE_FILE, 'w') as f: json.dump(data, f)
                st.success("Profile Saved!"); time.sleep(1); st.rerun()

# ---------------------------------------------------------
# 2. DASHBOARD (RESTORED 5 CARDS + CHARTS)
# ---------------------------------------------------------
elif "Dashboard" in selection:
    st.header(f"📊 {firm_name}")
    st.markdown("---")
    
    b2b = load_data(GST_FILE, ['Date', 'Invoice Value', 'Taxable', 'CGST', 'SGST', 'IGST', 'Buyer Name'])
    inward = load_data(INWARD_FILE, ['Date', 'Total Value', 'Taxable', 'CGST', 'SGST', 'IGST'])
    b2b['Invoice Value'] = pd.to_numeric(b2b['Invoice Value'], errors='coerce')
    inward['Total Value'] = pd.to_numeric(inward['Total Value'], errors='coerce')

    s_val = b2b['Invoice Value'].sum()
    p_val = inward['Total Value'].sum()
    gst_col = b2b[['CGST','SGST','IGST']].sum().sum()
    gst_pd = inward[['CGST','SGST','IGST']].sum().sum()
    prof = pd.to_numeric(b2b['Taxable'], errors='coerce').sum() - pd.to_numeric(inward['Taxable'], errors='coerce').sum()

    # RESTORED 5 CARDS
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Sales", f"₹{s_val:,.0f}")
    k2.metric("Inward", f"₹{p_val:,.0f}")
    k3.metric("GST Col.", f"₹{gst_col:,.0f}")
    k4.metric("GST Paid", f"₹{gst_pd:,.0f}")
    k5.metric("Gross Profit", f"₹{prof:,.0f}")

    st.markdown("---")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Monthly Sales")
        if not b2b.empty:
            b2b['Date'] = pd.to_datetime(b2b['Date'], format="%d-%m-%Y", errors='coerce')
            b2b['Month'] = b2b['Date'].dt.strftime('%b')
            chart_data = b2b.groupby('Month')['Invoice Value'].sum().reset_index()
            st.altair_chart(alt.Chart(chart_data).mark_bar().encode(x='Month', y='Invoice Value', color=alt.value('#4f46e5')), use_container_width=True)
    with c2:
        st.subheader("Top 5 Customers")
        if not b2b.empty:
            top = b2b.groupby('Buyer Name')['Invoice Value'].sum().sort_values(ascending=False).head(5).reset_index()
            st.dataframe(top, hide_index=True, use_container_width=True)

# ---------------------------------------------------------
# 3. CUSTOMER MASTER (RESTORED FIELDS)
# ---------------------------------------------------------
elif "Customer Master" in selection:
    st.header("👥 Customer Master")
    cust_df = load_data(CUSTOMER_FILE, ["Name", "GSTIN", "Mobile", "Email", "Address 1", "Address 2", "Address 3"])
    
    with st.expander("➕ Add New Customer", expanded=False):
        with st.form("add_cust"):
            name = st.text_input("Name")
            gst = st.text_input("GSTIN")
            c_mob, c_email = st.columns(2)
            with c_mob: mob = st.text_input("Mobile")
            with c_email: email = st.text_input("Email")
            a1 = st.text_input("Address 1")
            a2 = st.text_input("Address 2")
            a3 = st.text_input("Address 3")
            
            if st.form_submit_button("Save Customer", type="primary"):
                new_row = {"Name": name, "GSTIN": gst, "Mobile": mob, "Email": email, "Address 1": a1, "Address 2": a2, "Address 3": a3}
                cust_df = pd.concat([cust_df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(CUSTOMER_FILE, cust_df)
                st.success("Added!"); st.rerun()
    st.dataframe(cust_df, use_container_width=True)

# ---------------------------------------------------------
# 4. BILLING MASTER (FIXED GST, HSN & QR)
# ---------------------------------------------------------
elif "Billing Master" in selection:
    st.header("🧾 New Invoice")
    cust_df = load_data(CUSTOMER_FILE, ["Name", "GSTIN", "Address 1", "Address 2", "Address 3", "Mobile", "Email"])
    cust_names = ["Select"] + cust_df['Name'].tolist()
    
    c1, c2 = st.columns([2, 1])
    with c1: sel_name = st.selectbox("Customer", cust_names)
    with c2: inv_date = st.date_input("Date", date.today())
    inv_no = st.text_input("Invoice No", placeholder="Ex: FY25-26/001")
    
    # Init Items
    if "bill_items" not in st.session_state:
        st.session_state.bill_items = pd.DataFrame([{"Description": "", "HSN": "", "Qty": 1.0, "UOM": "", "Rate": 0.0, "GST": 18.0}])

    is_gst_active = profile.get('Is GST', 'No') == 'Yes'

    # Configure Columns (Hide HSN if no GST)
    col_config = {
        "Description": st.column_config.TextColumn("Description", width="large", required=True),
        "Qty": st.column_config.NumberColumn("Qty", format="%.2f"),
        "Rate": st.column_config.NumberColumn("Rate", format="₹ %.2f"),
        "Amount": st.column_config.NumberColumn("Amount", format="₹ %.2f", disabled=True),
    }
    
    if is_gst_active:
        col_config["HSN"] = st.column_config.TextColumn("HSN/SAC")
        col_config["GST"] = st.column_config.NumberColumn("GST %")
    else:
        # If not active, we still keep columns in DF but hide from view or ignore
        if "HSN" in st.session_state.bill_items.columns: st.session_state.bill_items = st.session_state.bill_items.drop(columns=["HSN", "GST"], errors='ignore')

    edited_items = st.data_editor(st.session_state.bill_items, num_rows="dynamic", use_container_width=True, key="bill_editor", column_config=col_config)
    
    # --- CALCULATION LOGIC RESTORED ---
    valid_items = edited_items[edited_items['Description'] != ""].copy()
    valid_items['Amount'] = valid_items['Qty'] * valid_items['Rate']
    
    # Calculate Tax per Item
    if is_gst_active and 'GST' in valid_items.columns:
        valid_items['TaxAmt'] = valid_items['Amount'] * (valid_items['GST'] / 100)
    else:
        valid_items['TaxAmt'] = 0.0

    taxable_subtotal = valid_items['Amount'].sum()
    total_tax = valid_items['TaxAmt'].sum()
    
    # Check Intra/Inter
    is_intra = True
    cust_gst = ""
    if sel_name != "Select":
        cust_row = cust_df[cust_df['Name'] == sel_name].iloc[0]
        cust_gst = str(cust_row.get('GSTIN', ''))
        my_gst = str(profile.get('GSTIN', ''))
        # Simple Logic: Check first 2 digits
        if len(cust_gst) >= 2 and len(my_gst) >= 2:
            if cust_gst[:2] != my_gst[:2]: is_intra = False
    
    cgst, sgst, igst = (0,0,0)
    if is_gst_active:
        if is_intra: cgst = total_tax/2; sgst = total_tax/2
        else: igst = total_tax
    
    grand_total = taxable_subtotal + cgst + sgst + igst
    
    # Display Totals
    st.markdown(f"**Subtotal:** ₹ {taxable_subtotal:,.2f} | **Tax:** ₹ {total_tax:,.2f} | **Total:** :green[₹ {grand_total:,.2f}]")

    if st.button("🚀 Generate Invoice", type="primary", use_container_width=True):
        if sel_name == "Select" or not inv_no: st.error("Select Customer and Enter Invoice No")
        else:
            cust_data = cust_row.to_dict(); cust_data['Date'] = inv_date.strftime("%d-%m-%Y")
            totals = {'taxable': taxable_subtotal, 'cgst': cgst, 'sgst': sgst, 'igst': igst, 'total': grand_total, 'is_intra': is_intra}
            
            path_main, path_lh = get_invoice_paths_dual(inv_date, inv_no, sel_name, profile)
            generate_pdf(profile, cust_data, valid_items.to_dict('records'), inv_no, path_main, totals, is_letterhead=False)
            
            gst_df = load_data(GST_FILE, [])
            new_rec = {'Bill No.': inv_no, 'Date': cust_data['Date'], 'Buyer Name': sel_name, 'GSTIN': cust_gst, 'Invoice Value': grand_total, 'Taxable': taxable_subtotal, 'CGST': cgst, 'SGST': sgst, 'IGST': igst, 'Items': json.dumps(valid_items.to_dict('records'))}
            save_data(GST_FILE, pd.concat([gst_df, pd.DataFrame([new_rec])], ignore_index=True))
            
            st.session_state.last_invoice_details = {'path': path_main, 'total': grand_total, 'cust': sel_name, 'mobile': cust_data['Mobile'], 'inv': inv_no}
            st.rerun()

    if st.session_state.last_invoice_details:
        det = st.session_state.last_invoice_details
        st.success(f"Generated {det['inv']}!")
        
        # --- WHATSAPP NOTE ---
        st.info("ℹ️ **WhatsApp Note:** Web browsers cannot attach files automatically. Please Download the PDF below first, then attach it in WhatsApp manually.")
        
        c_down, c_wa = st.columns(2)
        with c_down:
            with open(det['path'], "rb") as f: st.download_button("1. ⬇️ Download PDF", f, file_name=os.path.basename(det['path']), mime="application/pdf", type="primary", use_container_width=True)
        
        with c_wa:
            msg = get_invoice_whatsapp_msg(det['cust'], det['inv'], firm_name, date.today().strftime("%d-%m-%Y"), det['total'], profile.get('Mobile',''))
            # Mobile Deep Link
            wa_link = f"https://wa.me/91{det['mobile']}?text={urllib.parse.quote(msg)}"
            st.link_button("2. 📱 Open WhatsApp", wa_link, use_container_width=True)

# ---------------------------------------------------------
# 5. CUSTOMER LEDGER (RESTORED QR)
# ---------------------------------------------------------
elif "Customer Ledger" in selection:
    st.header("📒 Customer Ledger")
    cust_df = load_data(CUSTOMER_FILE, ["Name", "Mobile"])
    sel_cust = st.selectbox("Select Customer", ["Select"] + cust_df['Name'].tolist())
    
    if sel_cust != "Select":
        inv = load_data(GST_FILE, ['Buyer Name', 'Invoice Value']); rec = load_data(RECEIPT_FILE, ['Party Name', 'Amount'])
        c_inv = inv[inv['Buyer Name'] == sel_cust]
        c_rec = rec[rec['Party Name'] == sel_cust]
        
        bal = pd.to_numeric(c_inv['Invoice Value'], errors='coerce').sum() - pd.to_numeric(c_rec['Amount'], errors='coerce').sum()
        st.info(f"💰 Pending Balance: ₹ {bal:,.2f}")
        
        if bal > 0:
            st.markdown("### 📲 Payment QR")
            upi_id = profile.get('UPI ID', '')
            if upi_id:
                qr_path = generate_upi_qr(upi_id, firm_name, bal, f"Due from {sel_cust}")
                st.image(qr_path, width=200, caption="Scan to Pay")
            else: st.warning("Add UPI ID in Profile to see QR")

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
            sup = st.text_input("Supplier"); val = st.number_input("Total Value")
            if st.form_submit_button("Save"):
                new_row = {'Date': date.today().strftime("%d-%m-%Y"), 'Supplier Name': sup, 'Total Value': val}
                save_data(INWARD_FILE, pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)); st.rerun()
    st.dataframe(df, use_container_width=True)
