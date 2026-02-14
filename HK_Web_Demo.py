import streamlit as st
import pandas as pd
import json
import time
import io
import os
import base64
import urllib.parse
import random
import string
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Table, TableStyle
from reportlab.lib.units import inch
from streamlit_gsheets import GSheetsConnection
from PIL import Image

# --- PAGE CONFIG ---
st.set_page_config(page_title="HisaabKeeper Cloud", layout="wide", page_icon="🧾")

# --- STYLING CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .bill-header { 
        font-size: 26px; 
        font-weight: 700; 
        margin-bottom: 20px; 
        color: #1E1E1E; 
    }
    
    /* SUMMARY BOX STYLING */
    .bill-summary-box { 
        background-color: #f9f9f9; 
        padding: 20px; 
        border-radius: 8px; 
        border: 1px solid #e0e0e0; 
        margin-top: 20px;
        font-family: 'Roboto', sans-serif; 
    }
    
    .summary-row {
        display: flex;
        justify-content: space-between;
        margin-bottom: 8px;
        font-size: 16px;
        color: #333;
        font-family: 'Roboto', sans-serif;
    }
    
    .total-row { 
        display: flex;
        justify-content: space-between;
        font-size: 20px; 
        font-weight: bold; 
        border-top: 1px solid #ccc; 
        margin-top: 10px; 
        padding-top: 10px; 
        color: #000;
        font-family: 'Roboto', sans-serif;
    }
    
    /* POS Product Card */
    .product-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 10px;
        text-align: center;
        background-color: white;
        transition: 0.3s;
        height: 100%;
    }
    .product-price {
        color: #FF4B4B;
        font-weight: bold;
        font-size: 16px;
    }
    
    /* Button Width Fix */
    .stButton button { width: 100%; }
    
    /* Column alignment fix */
    div[data-testid="column"] { display: flex; flex-direction: column; justify-content: flex-end; }
</style>
""", unsafe_allow_html=True)

# --- EMAIL CONFIGURATION ---
SENDER_EMAIL = "your_email@gmail.com"  # <--- REPLACE THIS
SENDER_PASSWORD = "xxxx xxxx xxxx xxxx"  # <--- REPLACE THIS

# --- CONSTANTS ---
APP_NAME = "HisaabKeeper"
LOGO_FILE = "logo.png" 
SIGNATURE_FILE = "signature.png"

# --- STATE CODES ---
STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "25": "Daman & Diu", "26": "Dadra & Nagar Haveli", "27": "Maharashtra",
    "28": "Andhra Pradesh (Old)", "29": "Karnataka", "30": "Goa", "31": "Lakshadweep",
    "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman & Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other Territory",
    "99": "Centre Jurisdiction"
}

# --- HELPERS ---
def format_indian_currency(amount):
    try: amount = float(amount)
    except: return "₹ 0.00"
    s = "{:.2f}".format(amount)
    parts = s.split('.')
    integer_part = parts[0]
    if len(integer_part) > 3:
        last_three = integer_part[-3:]
        rest = integer_part[:-3]
        rest = re.sub(r"\B(?=(\d{2})+(?!\d))", ",", rest)
        formatted_integer = rest + "," + last_three
    else: formatted_integer = integer_part
    return f"₹ {formatted_integer}.{parts[1]}"

def get_whatsapp_web_link(mobile, msg):
    if not mobile: return None
    clean = re.sub(r'\D', '', str(mobile))
    if len(clean) == 10: clean = "91" + clean
    return f"https://web.whatsapp.com/send?phone={clean}&text={urllib.parse.quote(msg)}"

def generate_unique_id(): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
def is_valid_email(email): return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None
def is_valid_mobile(mobile): return re.match(r'^[6-9]\d{9}$', mobile) is not None
def is_valid_pan(pan): return re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', pan) is not None
def is_valid_gstin(gstin): return re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$', gstin) is not None

def image_to_base64(image_file):
    if image_file is None: return None
    try:
        img = Image.open(image_file)
        img.thumbnail((150, 150))
        buff = io.BytesIO()
        img = img.convert('RGB')
        img.save(buff, format="JPEG", quality=70)
        return base64.b64encode(buff.getvalue()).decode()
    except: return None

def base64_to_image(base64_string):
    if not base64_string or str(base64_string) == 'nan': return None
    try: return io.BytesIO(base64.b64decode(base64_string))
    except: return None

def send_otp_email(to_email, otp_code):
    if "your_email" in SENDER_EMAIL: st.error("Setup Error: Sender Email not configured."); return False
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL; msg['To'] = to_email; msg['Subject'] = f"{otp_code} is your HisaabKeeper Verification Code"
        body = f"Hello,\n\nOTP: {otp_code}\n\nRegards,\nHisaabKeeper"
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587); server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD); server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit(); return True
    except Exception as e: st.error(f"Failed to send email: {e}"); return False

def to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# --- DATABASE HANDLERS ---
def get_db_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def fetch_data(worksheet_name):
    conn = get_db_connection()
    schema = {
        "Users": ["UserID", "Username", "Password", "Business Name", "Tagline", "Is GST", "GSTIN", "PAN", "Mobile", "Email", "Template", "BillingStyle", "Addr1", "Addr2", "Pincode", "District", "State", "Bank Name", "Branch", "Account No", "IFSC", "UPI"],
        "Customers": ["UserID", "Name", "GSTIN", "Address 1", "Address 2", "Address 3", "State", "Mobile", "Email"],
        "Items": ["UserID", "Item Name", "Price", "UOM", "HSN", "Image"],
        "Invoices": ["UserID", "Bill No", "Date", "Buyer Name", "Items", "Total Taxable", "CGST", "SGST", "IGST", "Grand Total", "Ship Name", "Ship GSTIN", "Ship Addr1", "Ship Addr2", "Ship Addr3", "Payment Mode"],
        "Receipts": ["UserID", "Date", "Party Name", "Amount", "Note"],
        "Inward": ["UserID", "Date", "Supplier Name", "Total Value"]
    }
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
        if worksheet_name in schema:
            for col in schema[worksheet_name]:
                if col not in df.columns: df[col] = ""
            df = df[schema[worksheet_name]]
        return df
    except: return pd.DataFrame(columns=schema.get(worksheet_name, []))

def fetch_user_data(worksheet_name):
    if not st.session_state.get("user_id"): return pd.DataFrame()
    df = fetch_data(worksheet_name)
    if "UserID" in df.columns:
        return df[df["UserID"] == str(st.session_state["user_id"])]
    return df

def save_row_to_sheet(worksheet_name, new_row_dict):
    conn = get_db_connection()
    df = fetch_data(worksheet_name)
    if "UserID" not in new_row_dict: new_row_dict["UserID"] = st.session_state["user_id"]
    new_df = pd.DataFrame([new_row_dict])
    if df.empty: updated_df = new_df
    else: updated_df = pd.concat([df, new_df], ignore_index=True)
    try:
        conn.update(worksheet=worksheet_name, data=updated_df)
        st.cache_data.clear()
        return True
    except Exception as e:
        if "sheet" in str(e).lower() or "not found" in str(e).lower():
            try:
                conn.create(worksheet=worksheet_name, data=updated_df)
                st.cache_data.clear()
                return True
            except: return False
        return False

def save_bulk_data(worksheet_name, new_df_chunk):
    conn = get_db_connection()
    df = fetch_data(worksheet_name)
    if "UserID" not in new_df_chunk.columns: new_df_chunk["UserID"] = st.session_state["user_id"]
    else: new_df_chunk["UserID"] = new_df_chunk["UserID"].fillna(st.session_state["user_id"])
    updated_df = pd.concat([df, new_df_chunk], ignore_index=True) if not df.empty else new_df_chunk
    try:
        conn.update(worksheet=worksheet_name, data=updated_df)
        st.cache_data.clear()
        return True
    except:
        try:
            conn.create(worksheet=worksheet_name, data=updated_df)
            st.cache_data.clear()
            return True
        except: return False

def update_user_profile(updated_profile_dict):
    conn = get_db_connection()
    df = fetch_data("Users")
    idx = df[df["UserID"] == str(st.session_state["user_id"])].index
    if not idx.empty:
        for k, v in updated_profile_dict.items(): df.at[idx[0], k] = v
        try:
            conn.update(worksheet="Users", data=df)
            st.session_state.user_profile = df.iloc[idx[0]].to_dict()
            return True
        except: return False
    return False

# --- PDF GENERATOR ---
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
        y_contact -= 12
        c.drawCentredString(center_x, y_contact, seller.get('Addr2', ''))
        y_contact -= 12
        full_addr_3 = f"{seller.get('District', '')}, {seller.get('State', '')} - {seller.get('Pincode', '')}"
        c.drawCentredString(center_x, y_contact, full_addr_3)
        y_contact -= 12
        
        c.drawCentredString(center_x, y_contact, f"M: {seller.get('Mobile', '')} | E: {seller.get('Email', '')}")
    
    title_text = "TAX INVOICE" if seller.get('Is GST', 'No') == 'Yes' else "INVOICE"
    c.setFont(font_header, 14)
    c.drawCentredString(w/2, h-160, title_text)
    
    if theme != 'Modern' and not is_letterhead:
        c.line(30, h-165, w-30, h-165)
    
    y = h-190
    ship_data = buyer.get('Shipping', {})
    
    c.setFont(font_header, 10); c.drawString(40, y, "Bill To:")
    c.setFont(font_body, 10)
    c.drawString(40, y-15, buyer.get('Name', ''))
    
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
    c.drawString(40, addr_start_y, f"M: {buyer.get('Mobile', '')}  E: {buyer.get('Email', '')}")

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
        if ship_data.get('Addr3'):
            s_addr_y -= 12
            c.drawString(x_ship, s_addr_y, f"{ship_data.get('Addr3', '')}")

    x_inv = 400
    c.setFont(font_header, 10); c.drawString(x_inv, y, "Invoice Details:")
    c.setFont(font_body, 10)
    c.drawString(x_inv, y-15, f"Inv No: {inv_no}")
    c.drawString(x_inv, y-30, f"Date: {buyer.get('Date','')}")
    if seller.get('Is GST', 'No') == 'Yes':
        pos_code = buyer.get('POS Code', '24')
        c.drawString(x_inv, y-45, f"POS: {pos_code}-{STATE_CODES.get(pos_code, '')}")

    return h - 300 

def draw_footer_on_canvas(c, w, h, seller, font_header, font_body):
    foot_y = 130 
    c.line(30, foot_y + 90, w-30, foot_y + 90)
    
    c.setFont(font_header, 10); c.drawString(40, foot_y+75, "Bank Details:")
    c.setFont(font_body, 9)
    c.drawString(40, foot_y+60, f"Bank: {seller.get('Bank Name','')}")
    c.drawString(40, foot_y+48, f"Branch: {seller.get('Branch','')}")
    c.drawString(40, foot_y+36, f"A/c: {seller.get('Account No','')}")
    c.drawString(40, foot_y+24, f"IFSC: {seller.get('IFSC','')}")
    
    sign_y = foot_y + 50 
    c.drawRightString(w-40, sign_y, f"For, {seller.get('Business Name', '')}")
    
    if os.path.exists(SIGNATURE_FILE):
        try:
            sig_img = ImageReader(SIGNATURE_FILE)
            c.drawImage(sig_img, w-160, sign_y-55, width=1.4*inch, height=0.7*inch, mask='auto', preserveAspectRatio=True)
        except: pass

    c.drawRightString(w-40, sign_y-60, "Authorized Signatory")
    
    term_y = 50
    c.setFont(font_body, 7)
    terms = ["(1) We declare that this invoice shows the actual price of the goods/services described.", "(2) Subject to Local Jurisdiction.", "(3) Our responsibility ceases as soon as goods are delivered."]
    for term in terms: c.drawString(40, term_y, term); term_y -= 10
    
    c.setFillColor(colors.grey)
    c.setFont(font_body, 7)
    footer_msg = "This document is generated using HisaabKeeper to get demo or Free trial connect us on hello.hisaabkeeper@gmail.com or whats app us on +91 6353953790"
    c.drawCentredString(w/2, 15, footer_msg)
    c.setFillColor(colors.black)

def generate_pdf(seller, buyer, items, inv_no, path, totals, is_letterhead=False):
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4 
    
    theme = seller.get('Template', 'Simple')
    if theme == "Simple": theme = "Basic"
    
    if theme == 'Modern': 
        font_header = "Helvetica-Bold"; font_body = "Helvetica"
        accent_color = HexColor('#2C3E50'); text_color_head = colors.white; grid_color = colors.lightgrey
    elif theme == 'Formal':
        font_header = "Times-Bold"; font_body = "Times-Roman"
        accent_color = colors.white; text_color_head = colors.black; grid_color = colors.black
    else: 
        font_header = "Helvetica-Bold"; font_body = "Helvetica"
        accent_color = colors.grey; text_color_head = colors.whitesmoke; grid_color = colors.black

    is_gst_bill = seller.get('Is GST', 'No') == 'Yes'
    if is_gst_bill:
        header = ["Sr.\nNo.", "Description", "HSN/SAC", "Qty", "UOM", "Rate", "Amount"]
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
        if totals.get('is_intra', True):
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
        ('ALIGN', (0, summary_start), (len(header)-2,-1), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, grid_color)
    ]

    if theme == 'Modern':
        style_cmds.extend([
            ('BACKGROUND', (0,0), (-1,0), accent_color),
            ('TEXTCOLOR', (0,0), (-1,0), text_color_head),
            ('FONTNAME', (0,0), (-1,0), font_header),
            ('FONTNAME', (0, summary_start), (-1, -1), font_header),
            ('BACKGROUND', (0, -1), (-1, -1), colors.whitesmoke),
        ])
    
    for i in range(summary_start, len(data)): 
        style_cmds.append(('SPAN', (0,i), (span_cols,i)))
    
    main_table = Table(data, colWidths=col_widths)
    main_table.setStyle(TableStyle(style_cmds))

    hsn_table = None
    if is_gst_bill:
        tax_summary = {}
        for item in items:
            hsn_code = str(item.get('HSN', ''))
            gst_rate = float(item.get('GST Rate', 0))
            taxable_val = float(item['Qty']) * float(item['Rate'])
            key = (hsn_code, gst_rate)
            if key not in tax_summary: tax_summary[key] = {'taxable': 0.0, 'cgst': 0.0, 'sgst': 0.0, 'igst': 0.0, 'total': 0.0}
            tax_summary[key]['taxable'] += taxable_val
            if totals.get('is_intra', True):
                c_val = taxable_val * (gst_rate / 2 / 100); s_val = taxable_val * (gst_rate / 2 / 100); i_val = 0
            else:
                c_val = 0; s_val = 0; i_val = taxable_val * (gst_rate / 100)
            tax_summary[key]['cgst'] += c_val; tax_summary[key]['sgst'] += s_val; tax_summary[key]['igst'] += i_val; tax_summary[key]['total'] += (taxable_val + c_val + s_val + i_val)
        
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

    header_bottom_y = h - 300 
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
            if len(result) == 2: table_parts.append(result[0]); current_data = result[1]
            else: table_parts.append(current_data); break
    
    total_pages = len(table_parts)
    hsn_needs_new_page = False
    
    if hsn_table:
        htw, hth = hsn_table.wrapOn(c, w, h)
        last_part_h = table_parts[-1].wrapOn(c, w, h)[1]
        if (usable_height - last_part_h - 20) < hth:
            total_pages += 1
            hsn_needs_new_page = True

    for page_idx, part in enumerate(table_parts):
        y_start = draw_header_on_canvas(c, w, h, seller, buyer, inv_no, is_letterhead, theme, font_header, font_body)
        pw, ph = part.wrapOn(c, w, h)
        part.drawOn(c, 30, y_start - ph)
        current_y = y_start - ph - 20
        draw_footer_on_canvas(c, w, h, seller, font_header, font_body)
        c.setFont(font_body, 8)
        c.drawCentredString(w/2, 25, f"Page {page_idx+1} of {total_pages}") 
        
        if page_idx == len(table_parts) - 1:
            if hsn_table:
                htw, hth = hsn_table.wrapOn(c, w, h)
                if not hsn_needs_new_page: hsn_table.drawOn(c, 30, current_y - hth)
                else:
                    c.showPage()
                    y_start_new = draw_header_on_canvas(c, w, h, seller, buyer, inv_no, is_letterhead, theme, font_header, font_body)
                    draw_footer_on_canvas(c, w, h, seller, font_header, font_body)
                    c.drawCentredString(w/2, 25, f"Page {total_pages} of {total_pages}")
                    hsn_table.drawOn(c, 30, y_start_new - hth)
        c.showPage()
    c.save()

# --- SESSION STATE INITIALIZATION ---
if "user_id" not in st.session_state: st.session_state.user_id = None
if "user_profile" not in st.session_state: st.session_state.user_profile = {}
if "auth_mode" not in st.session_state: st.session_state.auth_mode = "login"
if "reg_success_msg" not in st.session_state: st.session_state.reg_success_msg = None
if "otp_generated" not in st.session_state: st.session_state.otp_generated = None
if "otp_email" not in st.session_state: st.session_state.otp_email = None
if "reg_temp_data" not in st.session_state: st.session_state.reg_temp_data = {}
if "last_generated_invoice" not in st.session_state: st.session_state.last_generated_invoice = None

if "bm_cust_idx" not in st.session_state: st.session_state.bm_cust_idx = 0
if "bm_date" not in st.session_state: st.session_state.bm_date = date.today()
if "reset_invoice_trigger" not in st.session_state: st.session_state.reset_invoice_trigger = False
if "menu_selection" not in st.session_state: st.session_state.menu_selection = "Dashboard"
if "pos_cart" not in st.session_state: st.session_state.pos_cart = []

if "im_name" not in st.session_state: st.session_state.im_name = ""
if "im_price" not in st.session_state: st.session_state.im_price = 0.0
if "im_uom" not in st.session_state: st.session_state.im_uom = "PCS"
if "im_hsn" not in st.session_state: st.session_state.im_hsn = ""

# --- LOGIN PAGE ---
def login_page():
    st.markdown("<h1 style='text-align:center;'>🔐 HisaabKeeper Login</h1>", unsafe_allow_html=True)
    if st.session_state.reg_success_msg:
        st.success(st.session_state.reg_success_msg); st.session_state.reg_success_msg = None

    if st.session_state.auth_mode == "login":
        with st.container():
            st.subheader("Sign In")
            with st.form("login_form"):
                user_input = st.text_input("Username")
                pwd = st.text_input("Password", type="password")
                if st.form_submit_button("Login", type="primary"):
                    df_users = fetch_data("Users")
                    if "Username" in df_users.columns:
                        df_users["Username"] = df_users["Username"].astype(str)
                        df_users["Password"] = df_users["Password"].astype(str)
                        user_row = df_users[(df_users["Username"] == user_input) & (df_users["Password"] == pwd)]
                        if not user_row.empty:
                            st.session_state.user_id = str(user_row.iloc[0]["UserID"])
                            st.session_state.user_profile = user_row.iloc[0].to_dict()
                            st.success("Login Successful!"); time.sleep(1); st.rerun()
                        else: st.error("Invalid Username or Password")
                    else: st.error("System Error: Users database missing.")
            st.markdown("---")
            col1, col2 = st.columns([0.7, 0.3])
            col1.write("New to HisaabKeeper?")
            if col2.button("Create Account"): st.session_state.auth_mode = "register"; st.session_state.otp_generated = None; st.rerun()

    elif st.session_state.auth_mode == "register":
        with st.container():
            st.subheader("Create New Account")
            if st.session_state.otp_generated is None:
                with st.form("reg_form"):
                    new_username = st.text_input("Choose Username (Unique)")
                    new_pwd = st.text_input("Choose Password", type="password")
                    bn = st.text_input("Business Name")
                    mob = st.text_input("Mobile Number (10 digits)")
                    em = st.text_input("Email ID")
                    if st.form_submit_button("Verify Email & Register"):
                        df_users = fetch_data("Users")
                        if not new_username or not new_pwd or not bn or not mob or not em: st.error("All fields mandatory.")
                        elif not is_valid_mobile(mob): st.error("Invalid Mobile Number!")
                        elif not is_valid_email(em): st.error("Invalid Email Format!")
                        elif not df_users.empty and "Username" in df_users.columns and new_username in df_users["Username"].astype(str).values:
                            st.error("Username already taken!")
                        else:
                            otp = str(random.randint(100000, 999999))
                            st.session_state.reg_temp_data = {"Username": new_username, "Password": new_pwd, "Business Name": bn, "Mobile": mob, "Email": em}
                            with st.spinner("Sending OTP..."):
                                if send_otp_email(em, otp):
                                    st.session_state.otp_generated = otp; st.session_state.otp_email = em; st.toast(f"OTP sent to {em}", icon="📧"); st.rerun()
                                else: st.error("Could not send email. Check SMTP.")
            else:
                st.info(f"OTP sent to {st.session_state.otp_email}")
                with st.form("otp_form"):
                    user_otp = st.text_input("Enter 6-Digit OTP")
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("Confirm Registration", type="primary"):
                        if user_otp == st.session_state.otp_generated:
                            unique_id = generate_unique_id()
                            final_data = st.session_state.reg_temp_data
                            new_user = {
                                "UserID": unique_id, "Username": final_data["Username"], "Password": final_data["Password"],
                                "Business Name": final_data["Business Name"], "Tagline": "", "GSTIN": "", "PAN": "",
                                "Mobile": final_data["Mobile"], "Email": final_data["Email"],
                                "Addr1": "", "Addr2": "", "Pincode": "", "District": "", "State": "", "Is GST": "No",
                                "Bank Name": "", "Branch": "", "Account No": "", "IFSC": "", "UPI": "", "Template": "Simple"
                            }
                            save_row_to_sheet("Users", new_user)
                            st.session_state.otp_generated = None; st.session_state.reg_temp_data = {}
                            st.session_state.reg_success_msg = f"🎉 Verified! Login as {final_data['Username']}"
                            st.session_state.auth_mode = "login"; st.rerun()
                        else: st.error("Incorrect OTP.")
                    if c2.form_submit_button("Cancel"): st.session_state.otp_generated = None; st.rerun()
            st.markdown("---")
            if st.button("Back to Login"): st.session_state.auth_mode = "login"; st.session_state.otp_generated = None; st.rerun()

# --- MAIN APP ---
def main_app():
    raw_profile = st.session_state.user_profile
    profile = {k: (v if str(v) != 'nan' else '') for k, v in raw_profile.items()}
    st.sidebar.title(f"🏢 {profile.get('Business Name', 'My Business')}")
    st.sidebar.caption(f"User: {profile.get('Username', 'User')}")
    if st.sidebar.button("Logout"):
        st.session_state.user_id = None; st.session_state.user_profile = {}; st.session_state.auth_mode = "login"; st.rerun()
    
    menu_options = ["Dashboard", "Customer Master", "Item Master", "Billing Master", "Ledger", "Inward", "Company Profile"]
    if st.session_state.menu_selection not in menu_options: st.session_state.menu_selection = "Dashboard"
    choice = st.sidebar.radio("Menu", menu_options, index=menu_options.index(st.session_state.menu_selection), key="nav_radio")
    if choice != st.session_state.menu_selection: st.session_state.menu_selection = choice; st.rerun()

    if choice == "Dashboard":
        st.header("📊 Dashboard")
        df_inv = fetch_user_data("Invoices")
        total_sales = 0
        if not df_inv.empty and "Grand Total" in df_inv.columns: 
            total_sales = pd.to_numeric(df_inv["Grand Total"], errors='coerce').sum()
        st.metric("Total Sales", format_indian_currency(total_sales))
        st.dataframe(df_inv.tail(5), use_container_width=True)

    elif choice == "Customer Master":
        st.header("👥 Customers")
        with st.expander("📤 Import / Export Data", expanded=False):
            c_downloads, c_upload = st.columns([1, 2])
            cust_cols = ["Name", "GSTIN", "Address 1", "Address 2", "Address 3", "State", "Mobile", "Email"]
            with c_downloads:
                cust_df = fetch_user_data("Customers")
                if not cust_df.empty and all(col in cust_df.columns for col in cust_cols): final_export = cust_df[cust_cols]
                else: final_export = pd.DataFrame(columns=cust_cols)
                excel_data = to_excel_bytes(final_export)
                st.download_button("⬇️ Download Data (Excel)", data=excel_data, file_name="MyCustomers.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                st.write("")
                template_df = pd.DataFrame(columns=cust_cols)
                template_bytes = to_excel_bytes(template_df)
                st.download_button("📄 Download Import Template", data=template_bytes, file_name="Import_Template.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            with c_upload:
                uploaded_file = st.file_uploader("⬆️ Upload Excel", type=["xlsx", "xls"])
                if uploaded_file is not None:
                    try:
                        imp_df = pd.read_excel(uploaded_file)
                        if st.button("Confirm Import", type="primary"):
                            if save_bulk_data("Customers", imp_df): st.success("Customers Imported Successfully!"); time.sleep(1); st.rerun()
                    except Exception as e: st.error(f"Error reading file: {e}")

        with st.expander("➕ Add New Customer", expanded=True):
            st.markdown("### Basic Details")
            c_name = st.text_input("👤 Customer Name")
            col_gst_in, col_gst_btn = st.columns([3, 1])
            c_gst = col_gst_in.text_input("🏢 GSTIN")
            col_gst_btn.write(""); col_gst_btn.write("") 
            if col_gst_btn.button("Fetch Details"): st.toast("Fetch from GST Portal: Coming Soon!", icon="⏳")
            st.divider()
            st.markdown("### 📍 Address Details")
            addr1 = st.text_input("Address Line 1")
            addr2 = st.text_input("Address Line 2")
            addr3 = st.text_input("Address Line 3")
            state_val = st.text_input("State (Required for Tax Calculation)")
            st.divider()
            st.markdown("### 📞 Contact Details")
            c1, c2 = st.columns(2)
            mob = c1.text_input("Mobile")
            email = c2.text_input("Email")
            st.write("")
            if st.button("Save Customer Data", type="primary"):
                if not c_name: st.error("Customer Name is required.")
                else:
                    if save_row_to_sheet("Customers", {
                        "Name": c_name, "GSTIN": c_gst, "Address 1": addr1, "Address 2": addr2, "Address 3": addr3, "State": state_val, "Mobile": mob, "Email": email
                    }):
                        st.success("Customer Saved Successfully!"); time.sleep(1); st.rerun()

        with st.expander("📋 Customer Database", expanded=False):
            view_df = fetch_user_data("Customers")
            if not view_df.empty: st.dataframe(view_df[cust_cols], use_container_width=True)
            else: st.info("No customers found.")

    elif choice == "Item Master":
        st.header("📦 Item Master")
        
        # --- ADD ITEM SECTION ---
        with st.expander("➕ Add New Item", expanded=True):
            i1, i2 = st.columns([1, 2])
            with i1:
                item_img = st.file_uploader("Product Image", type=['png', 'jpg', 'jpeg'], key="im_img_uploader")
            with i2:
                item_name = st.text_input("Item Name", key="im_name_input")
                ic1, ic2 = st.columns(2)
                item_price = ic1.number_input("Fixed Price", min_value=0.0, key="im_price_input")
                item_uom = ic2.selectbox("UOM", ["PCS", "KG", "LTR", "BOX", "MTR"], key="im_uom_input")
                item_hsn = st.text_input("HSN/SAC Code", key="im_hsn_input")
                
            if st.button("Save Item", type="primary"):
                if not item_name: st.error("Item Name is required")
                else:
                    img_str = image_to_base64(item_img) if item_img else ""
                    if save_row_to_sheet("Items", {
                        "Item Name": item_name, "Price": item_price, "UOM": item_uom, 
                        "HSN": item_hsn, "Image": img_str
                    }):
                        st.success("Item Saved!")
                        del st.session_state.im_name_input
                        del st.session_state.im_price_input
                        time.sleep(1); st.rerun()
        
        st.divider()
        st.subheader("📋 Item List")
        df_items = fetch_user_data("Items")
        if not df_items.empty:
            for i, row in df_items.iterrows():
                with st.container(border=True):
                    c_img, c_det, c_act = st.columns([1, 3, 1])
                    with c_img:
                        if row.get("Image"):
                            try: st.image(base64_to_image(row["Image"]), width=60)
                            except: st.write("No Img")
                        else: st.write("No Img")
                    with c_det:
                        st.markdown(f"**{row['Item Name']}**")
                        st.caption(f"Price: ₹{row['Price']} | HSN: {row['HSN']} | UOM: {row['UOM']}")
                    with c_act:
                        if st.button("✏️ Edit", key=f"edit_{i}"):
                            st.session_state.im_name_input = row['Item Name']
                            st.session_state.im_price_input = float(row['Price'])
                            st.session_state.im_hsn_input = row['HSN']
                            st.toast("Item details loaded above. Modify and Save.", icon="✏️")
                            st.rerun()
                        if st.button("🗑️ Delete", key=f"del_item_{i}"):
                            new_df = df_items.drop(index=i)
                            if save_bulk_data("Items", new_df):
                                st.success("Item Deleted!")
                                time.sleep(0.5); st.rerun()

    elif choice == "Billing Master":
        billing_style = profile.get("BillingStyle", "Default")
        
        if billing_style == "Retailers":
             st.info(f"🚧 You have selected the **{billing_style}** interface. This feature is coming soon! Please switch back to **Default** in Company Profile.")
        
        elif billing_style == "Customized Billing Master":
            st.markdown(f"<div class='bill-header'>🧾 New Invoice (Customized)</div>", unsafe_allow_html=True)
            df_cust = fetch_user_data("Customers")
            df_items = fetch_user_data("Items")

            c1, c2, c3 = st.columns([0.60, 0.15, 0.25], vertical_alignment="bottom")
            with c1:
                st.markdown("<p style='font-size:14px; font-weight:bold; margin-bottom:-10px;'>👤 Select Customer</p>", unsafe_allow_html=True)
                st.write("")
                cust_list = ["Select"] + df_cust["Name"].tolist() if not df_cust.empty else ["Select"]
                sel_cust_name = st.selectbox("Select Customer", cust_list, index=st.session_state.bm_cust_idx, key="bm_cust_val_pos", label_visibility="collapsed")
            with c2:
                st.write(""); st.write("")
                if st.button("➕ New", type="primary", help="Add New Customer", key="add_new_pos"):
                    st.session_state.menu_selection = "Customer Master"; st.rerun()
            with c3:
                st.markdown("<p style='font-size:14px; font-weight:bold; margin-bottom:-10px;'>📅 Invoice Date</p>", unsafe_allow_html=True)
                st.write("")
                inv_date_obj = st.date_input("Invoice Date", value=st.session_state.bm_date, format="DD/MM/YYYY", key="bm_date_val_pos", label_visibility="collapsed") 
                inv_date_str = inv_date_obj.strftime("%d/%m/%Y")
            
            st.write("")
            ic1, ic2 = st.columns([0.4, 0.6]) 
            with ic1:
                st.markdown("<p style='font-size:14px; font-weight:bold; margin-bottom:-10px;'>🧾 Invoice Number</p>", unsafe_allow_html=True)
                st.write("")
                val_inv = st.session_state.bm_invoice_no if "bm_invoice_no" in st.session_state else ""
                inv_no = st.text_input("Invoice Number", value=val_inv, label_visibility="collapsed", placeholder="Enter Inv No", key="bm_inv_val_pos")
                st.session_state.bm_invoice_no = inv_no

            st.divider()

            col_menu, col_cart = st.columns([2, 1])
            
            with col_menu:
                st.subheader("📦 Select Items")
                if not df_items.empty:
                    cols = st.columns(3)
                    for i, row in df_items.iterrows():
                        with cols[i % 3]:
                            with st.container(border=True):
                                if row.get("Image"):
                                    try: st.image(base64_to_image(row["Image"]), use_container_width=True)
                                    except: pass
                                st.markdown(f"**{row['Item Name']}**")
                                st.markdown(f"<span class='product-price'>₹ {row['Price']}</span>", unsafe_allow_html=True)
                                
                                cart_item = next((item for item in st.session_state.pos_cart if item['Description'] == row['Item Name']), None)
                                
                                if cart_item:
                                    b_minus, b_qty, b_plus = st.columns([0.2, 0.4, 0.2], vertical_alignment="center")
                                    if b_minus.button("➖", key=f"minus_{i}"):
                                        idx = st.session_state.pos_cart.index(cart_item)
                                        if st.session_state.pos_cart[idx]['Qty'] > 1:
                                            st.session_state.pos_cart[idx]['Qty'] -= 1
                                        else:
                                            st.session_state.pos_cart.pop(idx)
                                        st.rerun()
                                    
                                    b_qty.markdown(f"<div style='text-align:center; font-weight:bold; padding-top:5px;'>{int(cart_item['Qty'])}</div>", unsafe_allow_html=True)
                                    
                                    if b_plus.button("➕", key=f"plus_{i}"):
                                        idx = st.session_state.pos_cart.index(cart_item)
                                        st.session_state.pos_cart[idx]['Qty'] += 1
                                        st.rerun()
                                else:
                                    if st.button("Add", key=f"add_{i}"):
                                        st.session_state.pos_cart.append({
                                            "Description": row['Item Name'],
                                            "HSN": row.get('HSN', ''),
                                            "Qty": 1.0,
                                            "UOM": row.get('UOM', 'PCS'),
                                            "Rate": float(row['Price']),
                                            "GST Rate": 0.0
                                        })
                                        st.rerun()
                else:
                    st.info("No items found. Go to Item Master to add products.")

            with col_cart:
                st.subheader("🛒 Cart / Checkout")
                if st.session_state.pos_cart:
                    total_taxable = 0
                    grand_total = 0
                    
                    for idx, item in enumerate(st.session_state.pos_cart):
                        with st.container(border=True):
                            c_name, c_del = st.columns([4, 1])
                            c_name.write(f"**{item['Description']}**")
                            if c_del.button("🗑️", key=f"del_cart_{idx}"):
                                st.session_state.pos_cart.pop(idx)
                                st.rerun()
                            
                            c_qty, c_rate = st.columns(2)
                            new_qty = c_qty.number_input("Qty", value=float(item['Qty']), min_value=0.1, key=f"cart_qty_{idx}")
                            new_rate = c_rate.number_input("Rate", value=float(item['Rate']), min_value=0.0, key=f"cart_rate_{idx}")
                            
                            st.session_state.pos_cart[idx]['Qty'] = new_qty
                            st.session_state.pos_cart[idx]['Rate'] = new_rate
                            
                            line_amt = new_qty * new_rate
                            total_taxable += line_amt

                    st.divider()
                    pay_mode = st.radio("Payment Mode", ["Cash", "Online", "Credit"], horizontal=True)
                    
                    is_gst_active = profile.get("Is GST") == "Yes"
                    grand_total = total_taxable 

                    st.markdown(f"### Total: {format_indian_currency(total_taxable)}")
                    
                    if st.button("✅ Generate Invoice", type="primary", use_container_width=True):
                         if not sel_cust_name or sel_cust_name == "Select":
                             st.error("Select Customer!")
                         elif not inv_no:
                             st.error("Enter Invoice No!")
                         else:
                             # FIX: Fetch Customer Data First
                             cust_mob = ""
                             if sel_cust_name != "Select" and not df_cust.empty:
                                 cust_row_data = df_cust[df_cust["Name"] == sel_cust_name].iloc[0]
                                 cust_mob = str(cust_row_data.get("Mobile", ""))

                             items_json = json.dumps(st.session_state.pos_cart)
                             db_row = {
                                "Bill No": inv_no, "Date": inv_date_str, "Buyer Name": sel_cust_name, 
                                "Items": items_json, "Total Taxable": total_taxable, 
                                "Grand Total": grand_total, "Payment Mode": pay_mode,
                                "CGST": 0, "SGST": 0, "IGST": 0
                            }
                             
                             if save_row_to_sheet("Invoices", db_row):
                                 firm_name = profile.get('Business Name', 'Our Firm')
                                 msg_body = f"""Hi {sel_cust_name}, Invoice {inv_no} from {firm_name} generated."""
                                 
                                 pdf_buffer = io.BytesIO()
                                 buyer_data = df_cust[df_cust["Name"] == sel_cust_name].iloc[0].to_dict()
                                 buyer_data['Date'] = inv_date_str
                                 buyer_data['POS Code'] = '24'
                                 buyer_data['Shipping'] = {} # Ensure Shipping key exists
                                 
                                 totals = {'taxable': total_taxable, 'cgst': 0, 'sgst': 0, 'igst': 0, 'total': grand_total, 'is_intra': True}
                                 
                                 generate_pdf(profile, buyer_data, st.session_state.pos_cart, inv_no, pdf_buffer, totals)
                                 pdf_buffer.seek(0)
                                 
                                 st.session_state.last_generated_invoice = {
                                    "no": inv_no, "pdf_bytes": pdf_buffer,
                                    "wa_link": get_whatsapp_web_link(cust_mob, msg_body),
                                    "mail_link": None
                                }
                                 st.session_state.pos_cart = []
                                 st.rerun()
                else:
                    st.caption("Cart is Empty")
            
            if st.session_state.last_generated_invoice:
                 st.success("Invoice Generated!")
                 l = st.session_state.last_generated_invoice
                 c1, c2, c3 = st.columns(3)
                 c1.download_button("Download PDF", l['pdf_bytes'], "inv.pdf")
                 if l['wa_link']: c2.link_button("WhatsApp", l['wa_link'])
                 c3.button("Email", disabled=True)

        else:
            # --- DEFAULT INTERFACE ---
            st.markdown(f"<div class='bill-header'>🧾 New Invoice</div>", unsafe_allow_html=True)
            df_cust = fetch_user_data("Customers")
            
            c1, c2, c3 = st.columns([0.60, 0.15, 0.25], vertical_alignment="bottom")
            
            with c1:
                st.markdown("<p style='font-size:14px; font-weight:bold; margin-bottom:-10px;'>👤 Select Customer</p>", unsafe_allow_html=True)
                st.write("")
                cust_list = ["Select"] + df_cust["Name"].tolist() if not df_cust.empty else ["Select"]
                def update_cust(): st.session_state.bm_cust_idx = cust_list.index(st.session_state.bm_cust_val) if st.session_state.bm_cust_val in cust_list else 0
                sel_cust_name = st.selectbox("Select Customer", cust_list, index=st.session_state.bm_cust_idx, key="bm_cust_val", label_visibility="collapsed")
            
            with c2:
                st.write(""); st.write("")
                if st.button("➕ New", type="primary", help="Add New Customer"):
                    st.session_state.menu_selection = "Customer Master"; st.rerun()

            with c3:
                st.markdown("<p style='font-size:14px; font-weight:bold; margin-bottom:-10px;'>📅 Invoice Date</p>", unsafe_allow_html=True)
                st.write("")
                inv_date_obj = st.date_input("Invoice Date", value=st.session_state.bm_date, format="DD/MM/YYYY", key="bm_date_val", label_visibility="collapsed") 
                inv_date_str = inv_date_obj.strftime("%d/%m/%Y")
            
            cust_state = ""; cust_gstin = ""; cust_mob = ""; cust_email = ""
            if sel_cust_name != "Select" and not df_cust.empty:
                cust_row = df_cust[df_cust["Name"] == sel_cust_name].iloc[0]
                cust_gstin = str(cust_row.get("GSTIN", "")); cust_state = str(cust_row.get("State", ""))
                cust_mob = str(cust_row.get("Mobile", "")); cust_email = str(cust_row.get("Email", ""))
                c_info_addr = f"{cust_row.get('Address 1','')}, {cust_row.get('Address 2','')}"
                st.info(f"**GSTIN:** {cust_gstin if cust_gstin else 'Unregistered'} | **Mobile:** {cust_mob} | **Addr:** {c_info_addr}")

            st.write("")
            is_ship_diff = st.checkbox("🚢 Shipping Details", key="bm_ship_check")
            ship_data = {}
            if is_ship_diff:
                with st.container(border=True):
                    sc1, sc2 = st.columns(2)
                    ship_name = sc1.text_input("Ship Name"); ship_gst = sc2.text_input("Ship GSTIN")
                    ship_a1 = st.text_input("Ship Address 1"); ship_a2 = st.text_input("Ship Address 2"); ship_a3 = st.text_input("Ship Address 3")
                    ship_data = {"IsShipping": True, "Name": ship_name, "GSTIN": ship_gst, "Addr1": ship_a1, "Addr2": ship_a2, "Addr3": ship_a3}

            st.write("")
            st.markdown("<p style='font-size:14px; font-weight:bold; margin-bottom:-10px;'>🧾 Invoice Number</p>", unsafe_allow_html=True)
            st.write("")
            
            ic1, ic2 = st.columns([0.4, 0.6]) 
            with ic1:
                val_inv = st.session_state.bm_invoice_no if "bm_invoice_no" in st.session_state else ""
                inv_no = st.text_input("Invoice Number", value=val_inv, label_visibility="collapsed", placeholder="Enter Inv No", key="bm_inv_val")
                st.session_state.bm_invoice_no = inv_no

            df_inv_past = fetch_user_data("Invoices")
            past_str = "No past invoices"
            if not df_inv_past.empty:
                past_nos = df_inv_past["Bill No"].tail(3).tolist()
                past_str = ", ".join(map(str, past_nos))
            st.caption(f"📜 Last 3: {past_str}")

            st.divider()
            st.markdown("#### 📦 Product / Service Details")

            if st.session_state.reset_invoice_trigger:
                st.session_state.invoice_items_grid = pd.DataFrame([{"Description": "", "HSN": "", "Qty": 1.0, "UOM": "PCS", "Rate": 0.0, "GST Rate": 0.0}])
                st.session_state.bm_invoice_no = "" 
                st.session_state.reset_invoice_trigger = False
                st.rerun()

            if "invoice_items_grid" not in st.session_state:
                st.session_state.invoice_items_grid = pd.DataFrame([{"Description": "", "HSN": "", "Qty": 1.0, "UOM": "PCS", "Rate": 0.0, "GST Rate": 0.0}])

            edited_items = st.data_editor(
                st.session_state.invoice_items_grid, num_rows="dynamic", use_container_width=True,
                column_config={
                    "Description": st.column_config.TextColumn("Item Name", required=True),
                    "HSN": st.column_config.TextColumn("HSN/SAC Code"),
                    "Qty": st.column_config.NumberColumn("Qty", required=True, default=1.0),
                    "UOM": st.column_config.SelectboxColumn("UOM", options=["PCS", "KG", "LTR", "MTR", "BOX", "SET"], required=True, default="PCS"),
                    "Rate": st.column_config.NumberColumn("Item Rate", required=True, default=0.0),
                    "GST Rate": st.column_config.NumberColumn("GST Rate %", required=True, default=0.0, min_value=0, max_value=28)
                }, key="final_invoice_editor_polished_v8"
            )

            valid_items = edited_items[edited_items["Description"] != ""].copy()
            valid_items["Qty"] = pd.to_numeric(valid_items["Qty"], errors='coerce').fillna(0)
            valid_items["Rate"] = pd.to_numeric(valid_items["Rate"], errors='coerce').fillna(0)
            valid_items["GST Rate"] = pd.to_numeric(valid_items["GST Rate"], errors='coerce').fillna(0)
            
            valid_items["Base Amount"] = valid_items["Qty"] * valid_items["Rate"]
            valid_items["Tax Amount"] = valid_items["Base Amount"] * (valid_items["GST Rate"] / 100)
            
            total_taxable = valid_items["Base Amount"].sum()
            total_tax_val = valid_items["Tax Amount"].sum()
            grand_total = total_taxable + total_tax_val
            
            user_state = profile.get("State", "").strip().lower()
            cust_state_clean = cust_state.strip().lower()
            user_gstin = profile.get("GSTIN", "")
            
            is_inter_state = False
            if len(user_gstin) >= 2 and len(cust_gstin) >= 2:
                if user_gstin[:2] != cust_gstin[:2]: is_inter_state = True
            elif user_state and cust_state_clean:
                if user_state != cust_state_clean: is_inter_state = True
                
            cgst_val = 0.0; sgst_val = 0.0; igst_val = 0.0
            if is_inter_state: igst_val = total_tax_val
            else: cgst_val = total_tax_val / 2; sgst_val = total_tax_val / 2

            st.write("")
            c_spacer, c_totals = st.columns([1.5, 1])
            
            with c_totals:
                gst_label = "IGST" if is_inter_state else "CGST+SGST"
                gst_val_numeric = igst_val if is_inter_state else (cgst_val + sgst_val)
                gst_val_fmt = format_indian_currency(gst_val_numeric)
                
                html_content = f"""
                <div style="background-color: #F0F2F6; padding: 20px; border-radius: 15px; border-left: 5px solid #FF4B4B;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                        <span style="font-weight: 500; color: #555;">Sub Total</span>
                        <span style="font-weight: 600; color: #333;">{format_indian_currency(total_taxable)}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <span style="font-weight: 500; color: #555;">{gst_label}</span>
                        <span style="font-weight: 600; color: #333;">{gst_val_fmt}</span>
                    </div>
                    <hr style="margin: 10px 0; border-color: #ddd;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 18px; font-weight: bold; color: #000;">Grand Total</span>
                        <span style="font-size: 22px; font-weight: bold; color: #FF4B4B;">{format_indian_currency(grand_total)}</span>
                    </div>
                </div>
                """
                st.markdown(html_content, unsafe_allow_html=True)
                
                st.write("")
                if st.button("🚀 Save & Generate Invoice", type="primary", use_container_width=True):
                    is_duplicate = False
                    if not df_inv_past.empty and inv_no in df_inv_past["Bill No"].astype(str).values: is_duplicate = True
                    
                    if sel_cust_name == "Select": st.error("Please Select a Customer")
                    elif not inv_no: st.error("Please Enter Invoice Number")
                    elif is_duplicate: st.error(f"Invoice Number {inv_no} already exists!")
                    elif valid_items.empty: st.error("Please add at least one item")
                    else:
                        items_json = json.dumps(valid_items.to_dict('records'))
                        db_row = {
                            "Bill No": inv_no, "Date": inv_date_str, "Buyer Name": sel_cust_name, 
                            "Items": items_json, "Total Taxable": total_taxable, 
                            "CGST": cgst_val, "SGST": sgst_val, "IGST": igst_val, "Grand Total": grand_total,
                            "Ship Name": ship_data.get("Name",""), "Ship GSTIN": ship_data.get("GSTIN",""),
                            "Ship Addr1": ship_data.get("Addr1",""), "Ship Addr2": ship_data.get("Addr2",""), "Ship Addr3": ship_data.get("Addr3","")
                        }
                        
                        if save_row_to_sheet("Invoices", db_row):
                            firm_name = profile.get('Business Name', 'Our Firm')
                            contact = f"{profile.get('Mobile','')}"
                            msg_body = f"""Hi *{sel_cust_name}*,

Greetings from *{firm_name}*. I’m sending over the invoice *{inv_no}* dated *{inv_date_str}* for *{format_indian_currency(grand_total)}*. The details are included in the attachment for your review.

Thanks again for your cooperation and continued support.

*{firm_name}*
{contact}

------------------------------------------
This mail is autogenerated through the *HisaabKeeper! Billing Software*.

To get demo or Free trial connect us on hello.hisaabkeeper@gmail.com or whatsapp us on +91 6353953790"""
                            
                            pdf_buffer = io.BytesIO()
                            
                            totals_for_pdf = {
                                'taxable': total_taxable, 
                                'cgst': cgst_val, 
                                'sgst': sgst_val, 
                                'igst': igst_val, 
                                'total': grand_total,
                                'is_intra': not is_inter_state 
                            }
                            
                            profile['Template'] = profile.get('Template', 'Simple')
                            buyer_data_for_pdf = df_cust[df_cust["Name"] == sel_cust_name].iloc[0].to_dict()
                            buyer_data_for_pdf['Date'] = inv_date_str
                            if is_inter_state: buyer_data_for_pdf['POS Code'] = "Inter" 
                            else: buyer_data_for_pdf['POS Code'] = "24" 
                            buyer_data_for_pdf['Shipping'] = ship_data # PASS SHIPPING DATA

                            generate_pdf(profile, buyer_data_for_pdf, 
                                         valid_items.to_dict('records'), inv_no, pdf_buffer, 
                                         totals_for_pdf, is_letterhead=False) 
                            
                            pdf_buffer.seek(0)
                            
                            st.session_state.last_generated_invoice = {
                                "no": inv_no, 
                                "pdf_bytes": pdf_buffer,
                                "wa_link": get_whatsapp_web_link(cust_mob, msg_body) if cust_mob else None,
                                "mail_link": f"mailto:{cust_email}?subject={urllib.parse.quote(f'Invoice {inv_no} from {firm_name}')}&body={urllib.parse.quote(msg_body)}" if cust_email else None
                            }
                            
                            st.session_state.bm_cust_idx = 0
                            st.session_state.bm_date = date.today()
                            st.session_state.reset_invoice_trigger = True 
                            st.rerun()

            # --- SUCCESS ACTIONS ---
            if st.session_state.last_generated_invoice:
                last_inv = st.session_state.last_generated_invoice
                st.success(f"✅ Invoice {last_inv['no']} Generated Successfully!")
                
                ac1, ac2, ac3 = st.columns(3)
                ac1.download_button("⬇️ Download PDF", last_inv["pdf_bytes"], f"Invoice_{last_inv['no']}.pdf", "application/pdf", use_container_width=True)
                
                wa_link = last_inv.get("wa_link")
                if wa_link: ac2.link_button("📱 WhatsApp Web", wa_link, use_container_width=True)
                else: ac2.button("📱 WhatsApp", disabled=True, use_container_width=True, help="No Mobile Number")
                
                mail_link = last_inv.get("mail_link")
                if mail_link: ac3.link_button("📧 Email", mail_link, use_container_width=True)
                else: ac3.button("📧 Email", disabled=True, use_container_width=True, help="No Email ID")
                
                if st.button("Create Another Invoice"):
                    st.session_state.last_generated_invoice = None
                    st.rerun()

    elif choice == "Ledger":
        st.header("📒 Ledger")
        df_cust = fetch_user_data("Customers")
        sel_cust = st.selectbox("Customer", ["Select"] + df_cust["Name"].tolist())
        if sel_cust != "Select":
            df_inv = fetch_user_data("Invoices")
            df_rec = fetch_user_data("Receipts")
            total_billed = 0; total_paid = 0
            if not df_inv.empty and "Grand Total" in df_inv.columns:
                total_billed = pd.to_numeric(df_inv[df_inv["Buyer Name"] == sel_cust]["Grand Total"], errors='coerce').sum()
            if not df_rec.empty and "Amount" in df_rec.columns:
                total_paid = pd.to_numeric(df_rec[df_rec["Party Name"] == sel_cust]["Amount"], errors='coerce').sum()
            st.metric("Pending Balance", format_indian_currency(total_billed - total_paid))
            with st.expander("Add Receipt"):
                amt = st.number_input("Amount Received")
                if st.button("Save Receipt"):
                    save_row_to_sheet("Receipts", {"Date": str(date.today()), "Party Name": sel_cust, "Amount": amt, "Note": "Payment"})
                    st.success("Saved!"); st.rerun()

    elif choice == "Inward":
        st.header("🚚 Inward Supply")
        with st.form("inw"):
            sup = st.text_input("Supplier"); val = st.number_input("Value")
            if st.form_submit_button("Save"):
                save_row_to_sheet("Inward", {"Date": str(date.today()), "Supplier Name": sup, "Total Value": val})
                st.success("Saved")

    elif choice == "Company Profile":
        st.header("⚙️ Company Profile")
        st.info(f"🔒 System User ID: {st.session_state.user_id} (16-Digit Unique Code)")
        st.subheader("Tax Configuration")
        col_tax1, col_tax2 = st.columns([1, 2])
        current_gst_val = profile.get("Is GST", "No")
        gst_selection = col_tax1.radio("Registered in GST?", ["Yes", "No"], index=0 if current_gst_val == "Yes" else 1, horizontal=True)
        with st.form("edit_profile"):
            with st.expander("🏢 Company Details", expanded=True):
                c1, c2 = st.columns(2)
                bn = c1.text_input("Business Name", value=profile.get("Business Name", ""))
                tag = c2.text_input("Tagline", value=profile.get("Tagline", ""))
                c3, c4, c5 = st.columns(3)
                logo = c3.file_uploader("Upload Company Logo (PNG/JPG)", type=['png', 'jpg'])
                signature = c4.file_uploader("Upload Signature (PNG/JPG)", type=['png', 'jpg'])
                
                # Retrieve current values properly to set index
                current_style = profile.get("BillingStyle", "Default")
                style_options = ["Default", "Retailers", "Customized Billing Master"]
                try: style_idx = style_options.index(current_style)
                except: style_idx = 0
                
                billing_style_input = st.selectbox("Billing Interface Style", style_options, index=style_idx)
                
                current_template = profile.get("Template", "Simple")
                template_options = ["Simple", "Modern", "Formal"]
                try: temp_idx = template_options.index(current_template)
                except: temp_idx = 0
                
                template = c5.selectbox("PDF Template", template_options, index=temp_idx)

                c6, c7 = st.columns(2)
                mob = c6.text_input("Business Mobile", value=profile.get("Mobile", ""))
                em = c7.text_input("Business Email", value=profile.get("Email", ""))
                tax_id_val = ""
                if gst_selection == "Yes":
                    tax_id_val = st.text_input("GSTIN (e.g. 24ABCDE1234F1Z5)", value=profile.get("GSTIN", ""))
                    pan_val = profile.get("PAN", "")
                else:
                    tax_id_val = st.text_input("PAN Number (e.g. ABCDE1234F)", value=profile.get("PAN", ""))
                    pan_val = tax_id_val
                    gstin_val = ""
            with st.expander("📍 Address Details", expanded=False):
                a1 = st.text_input("Address Line 1", value=profile.get("Addr1", ""))
                a2 = st.text_input("Address Line 2", value=profile.get("Addr2", ""))
                ac1, ac2, ac3 = st.columns(3)
                pincode = ac1.text_input("Pincode", value=profile.get("Pincode", ""))
                dist = ac2.text_input("District", value=profile.get("District", ""))
                state = ac3.text_input("State", value=profile.get("State", ""))
            with st.expander("🏦 Bank & Payment Details", expanded=False):
                bc1, bc2 = st.columns(2)
                bank_name = bc1.text_input("Bank Name", value=profile.get("Bank Name", ""))
                branch = bc2.text_input("Branch Name", value=profile.get("Branch", ""))
                bc3, bc4 = st.columns(2)
                acc_no_raw = bc3.text_input("Account Number (Numeric Only)", value=profile.get("Account No", ""))
                # Auto-remove .0
                if str(acc_no_raw).endswith('.0'): acc_no_raw = str(acc_no_raw)[:-2]
                acc_no = acc_no_raw

                ifsc = bc4.text_input("IFSC Code", value=profile.get("IFSC", ""))
                upi = st.text_input("UPI ID (must contain @)", value=profile.get("UPI", ""))
            if st.form_submit_button("💾 Update Company Profile"):
                errors = []
                final_gstin = ""; final_pan = ""; clean_tax_val = tax_id_val.upper()
                if gst_selection == "Yes":
                    if not is_valid_gstin(clean_tax_val): errors.append("Invalid GSTIN! Format: 24ABCDE1234F1Z5")
                    final_gstin = clean_tax_val
                else:
                    if not is_valid_pan(clean_tax_val): errors.append("Invalid PAN! Format: ABCDE1234F")
                    final_pan = clean_tax_val
                
                if acc_no and not str(acc_no).isdigit(): errors.append("Account Number must contain only digits.")
                if upi and "@" not in upi: errors.append("Invalid UPI ID (must contain '@').")
                
                if errors:
                    for e in errors: st.error(e)
                else:
                    # SAVE FILES
                    if logo is not None:
                        with open(LOGO_FILE, "wb") as f:
                            f.write(logo.getbuffer())
                    
                    if signature is not None:
                        with open(SIGNATURE_FILE, "wb") as f:
                            f.write(signature.getbuffer())

                    updated_data = {
                        "Business Name": bn, "Tagline": tag, "Mobile": mob, "Email": em, 
                        "Template": template, "BillingStyle": billing_style_input,
                        "Is GST": gst_selection, "GSTIN": final_gstin, "PAN": final_pan,
                        "Addr1": a1, "Addr2": a2, "Pincode": pincode, "District": dist, "State": state,
                        "Bank Name": bank_name, "Branch": branch, "Account No": acc_no, "IFSC": ifsc, "UPI": upi
                    }
                    if update_user_profile(updated_data): st.success("Profile Updated Successfully!"); time.sleep(1); st.rerun()

if st.session_state.user_id: main_app()
else: login_page()
    
