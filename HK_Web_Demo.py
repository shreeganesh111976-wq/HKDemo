import streamlit as st
import pandas as pd
import json
import time
import io
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
from reportlab.platypus import Table, TableStyle
from reportlab.lib.units import inch
from streamlit_gsheets import GSheetsConnection

# --- PAGE CONFIG ---
st.set_page_config(page_title="HisaabKeeper Cloud", layout="wide", page_icon="🧾")

# --- STYLING CSS (From your design) ---
st.markdown("""
<style>
    .bill-header { font-size: 24px; font-weight: bold; margin-bottom: 20px; }
    .bill-summary-box { background-color: #f9f9f9; padding: 15px; border-radius: 10px; border: 1px solid #ddd; }
    .total-row { font-size: 20px; font-weight: bold; border-top: 1px solid #ccc; margin-top: 10px; padding-top: 5px; }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
APP_NAME = "HisaabKeeper"
# Add your email config here
SENDER_EMAIL = "your_email@gmail.com" 
SENDER_PASSWORD = "xxxx xxxx xxxx xxxx"

# --- GOOGLE SHEETS CONNECTION HANDLER ---
def get_db_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def fetch_data(worksheet_name):
    conn = get_db_connection()
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
        return df
    except:
        return pd.DataFrame()

def save_row_to_sheet(worksheet_name, new_row_dict):
    conn = get_db_connection()
    df = fetch_data(worksheet_name)
    new_df = pd.DataFrame([new_row_dict])
    updated_df = pd.concat([df, new_df], ignore_index=True) if not df.empty else new_df
    try:
        conn.update(worksheet=worksheet_name, data=updated_df)
        st.cache_data.clear()
    except Exception as e: st.error(f"Error: {e}")

# --- HELPER FUNCTIONS ---
def get_whatsapp_web_link(mobile, msg):
    if not mobile: return None
    clean = re.sub(r'\D', '', str(mobile))
    if len(clean) == 10: clean = "91" + clean
    return f"https://web.whatsapp.com/send?phone={clean}&text={urllib.parse.quote(msg)}"

# --- PDF GENERATOR (Simplified for brevity, ensure you keep your full logic) ---
def generate_pdf_buffer(seller, buyer, items, inv_no, inv_date, totals, ship_details=None):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 18); c.drawCentredString(w/2, h-50, str(seller.get('Business Name', 'My Firm')))
    # ... (Your existing PDF logic here) ...
    c.drawString(40, h-120, f"Bill To: {buyer.get('Name','')}")
    c.drawRightString(w-40, h-120, f"Inv: {inv_no} | Date: {inv_date}")
    # ... (Items Loop) ...
    c.save()
    buffer.seek(0)
    return buffer

# --- SESSION STATE ---
if "user_id" not in st.session_state: st.session_state.user_id = None
if "user_profile" not in st.session_state: st.session_state.user_profile = {}
if "billing_key" not in st.session_state: st.session_state.billing_key = str(random.randint(1000, 9999))
if "last_generated_invoice" not in st.session_state: st.session_state.last_generated_invoice = None

def main_app():
    profile = st.session_state.user_profile
    st.sidebar.title(f"🏢 {profile.get('Business Name', 'My Business')}")
    
    menu = st.sidebar.radio("Menu", ["Dashboard", "Billing Master", "Customer Master", "Company Profile"])

    if menu == "Billing Master":
        # --- 1. HEADER & CUSTOMER SELECT ---
        st.markdown(f"<div class='bill-header'>🧾 New Invoice</div>", unsafe_allow_html=True)
        
        # Load Data
        df_cust = fetch_data("Customers")
        all_customers = ["Select Customer"] + list(df_cust['Name'].unique()) if not df_cust.empty else ["Select Customer"]
        
        c1, c2, c3 = st.columns([2, 1, 1])
        
        with c1:
            st.markdown("**👤 Select Customer**")
            sel_cust_name = st.selectbox("Customer", all_customers, label_visibility="collapsed", key=f"cust_box_{st.session_state.billing_key}")
            cust_row = {}
            if sel_cust_name != "Select Customer" and not df_cust.empty:
                cust_row = df_cust[df_cust['Name'] == sel_cust_name].iloc[0]
                st.caption(f"GSTIN: {cust_row.get('GSTIN','N/A')} | Mob: {cust_row.get('Mobile','N/A')}")

        with c2:
            st.markdown("**&nbsp;**", unsafe_allow_html=True)
            if st.button("➕ Add New", type="primary"): 
                st.toast("Go to Customer Master")

        with c3:
            st.markdown("**📅 Invoice Date**")
            inv_date = st.date_input("Date", datetime.now(), label_visibility="collapsed", key=f"date_box_{st.session_state.billing_key}")

        st.markdown("---")

        # --- 2. SHIPPING DETAILS ---
        c_ship_label, c_ship_box = st.columns([1, 3])
        with c_ship_label: st.markdown("**🚢 Shipping Details**")
        with c_ship_box: use_shipping = not st.checkbox("Shipping address is same as billing address", value=True)
        
        ship_data = {}
        if use_shipping:
            s1, s2 = st.columns(2)
            with s1: st.markdown("**Name**"); ship_name = st.text_input("Ship Name", label_visibility="collapsed")
            with s2: st.markdown("**GSTIN**"); ship_gst = st.text_input("Ship GSTIN", label_visibility="collapsed")
            
            st.markdown("**📍 Address**")
            sa1, sa2, sa3 = st.columns(3)
            with sa1: st.caption("Address Line 1"); ship_a1 = st.text_input("S1", label_visibility="collapsed")
            with sa2: st.caption("Address Line 2"); ship_a2 = st.text_input("S2", label_visibility="collapsed")
            with sa3: st.caption("Address Line 3"); ship_a3 = st.text_input("S3", label_visibility="collapsed")
            ship_data = {"IsShipping": True, "Name": ship_name, "GSTIN": ship_gst, "Addr1": ship_a1, "Addr2": ship_a2, "Addr3": ship_a3}

        st.markdown("---")

        # --- 3. INVOICE NUMBER ---
        c_inv_no, c_spacer = st.columns([1, 2])
        with c_inv_no:
            st.markdown("**🧾 Invoice Number**")
            inv_no_input = st.text_input("Inv No", label_visibility="collapsed", key=f"inv_no_{st.session_state.billing_key}")
            
            # Last 3 logic
            df_hist = fetch_data("Invoices")
            if not df_hist.empty and 'Bill No' in df_hist.columns:
                last_3 = df_hist['Bill No'].tail(3).tolist()
                st.caption(f"📜 Last 3: {', '.join(map(str, last_3))}")

        # --- 4. PRODUCT TABLE (Safe Render) ---
        st.markdown("**📦 Product / Service Details**")
        
        # Fresh Grid Init
        if "grid_df" not in st.session_state:
            st.session_state.grid_df = pd.DataFrame([{"Description": "", "HSN": "", "Qty": 1.0, "UOM": "PCS", "Rate": 0.0, "GST": 0.0}])

        edited_items = st.data_editor(
            st.session_state.grid_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Description": st.column_config.TextColumn("Item Name", required=True),
                "HSN": st.column_config.TextColumn("HSN/SAC"),
                "Qty": st.column_config.NumberColumn("Qty", default=1.0),
                "Rate": st.column_config.NumberColumn("Rate", format="₹ %.2f"),
                "GST": st.column_config.NumberColumn("GST %", default=0.0)
            },
            key=f"editor_{st.session_state.billing_key}"
        )

        # --- 5. CALCULATIONS & TOTALS ---
        if not edited_items.empty:
            valid_items = edited_items[edited_items['Description'].astype(str).str.strip() != ""].copy()
            
            # Safe Conversions
            for col in ['Qty', 'Rate', 'GST']:
                valid_items[col] = pd.to_numeric(valid_items[col], errors='coerce').fillna(0)

            if not valid_items.empty:
                # Math
                valid_items['Amount'] = valid_items['Qty'] * valid_items['Rate']
                valid_items['TaxAmt'] = valid_items['Amount'] * (valid_items['GST'] / 100)
                
                taxable = valid_items['Amount'].sum()
                total_tax_amt = valid_items['TaxAmt'].sum()
                
                # Tax Logic (State based)
                seller_gst = str(profile.get('GSTIN', ''))
                seller_state = str(profile.get('State', '')).strip().lower()
                
                buyer_gst = str(cust_row.get('GSTIN', ''))
                buyer_state = str(cust_row.get('State', '')).strip().lower()
                
                is_intra = True # Default
                # 1. GSTIN Check
                if len(seller_gst) >= 2 and len(buyer_gst) >= 2:
                    if seller_gst[:2] != buyer_gst[:2]: is_intra = False
                # 2. State Fallback
                elif seller_state and buyer_state:
                    if seller_state != buyer_state: is_intra = False
                
                if is_intra:
                    cgst = total_tax_amt/2; sgst = total_tax_amt/2; igst = 0; tax_lbl = "CGST+SGST"
                else:
                    cgst = 0; sgst = 0; igst = total_tax_amt; tax_lbl = "IGST"
                
                total = taxable + total_tax_amt

                # --- TOTALS DISPLAY (Your Exact HTML Layout) ---
                c_blank, c_sum = st.columns([2, 1])
                with c_sum:
                    st.markdown("<div class='bill-summary-box'>", unsafe_allow_html=True)
                    st.markdown(f"**Sub Total:** <span style='float:right'>₹ {taxable:,.2f}</span>", unsafe_allow_html=True)
                    st.markdown(f"**{tax_lbl}:** <span style='float:right'>₹ {total_tax_amt:,.2f}</span>", unsafe_allow_html=True)
                    st.markdown(f"<div class='total-row'>Total: <span style='float:right'>₹ {total:,.2f}</span></div>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    st.write("")
                    
                    # --- GENERATE BUTTON ---
                    if st.button("🚀 Save & Generate Invoice", type="primary", use_container_width=True):
                        # Validation
                        dupe_check = False
                        if not df_hist.empty and 'Bill No' in df_hist.columns:
                            if str(inv_no_input) in df_hist['Bill No'].astype(str).values: dupe_check = True

                        if sel_cust_name == "Select Customer": st.error("⚠️ Select a Customer!")
                        elif not inv_no_input: st.error("⚠️ Enter Invoice Number!")
                        elif dupe_check: st.error("❌ Invoice Number already exists!")
                        else:
                            # Save
                            items_json = json.dumps(valid_items.to_dict('records'))
                            db_row = {
                                "Bill No": inv_no_input, "Date": inv_date.strftime("%d-%m-%Y"), 
                                "Buyer Name": sel_cust_name, "Items": items_json, "Grand Total": total,
                                "Ship Name": ship_data.get("Name","")
                            }
                            save_row_to_sheet("Invoices", db_row)
                            
                            # Success Data
                            firm_name = profile.get('Business Name', 'My Firm')
                            contact = profile.get('Mobile', '')
                            msg = f"Hi {sel_cust_name},\n\nSending Invoice {inv_no_input} for ₹{total:,.2f}.\n\nRegards,\n{firm_name}"
                            
                            st.session_state.last_generated_invoice = {
                                "no": inv_no_input,
                                "wa_link": get_whatsapp_web_link(cust_row.get("Mobile"), msg),
                                "pdf_bytes": generate_pdf_buffer(profile, cust_row.to_dict(), valid_items.to_dict('records'), inv_no_input, inv_date, {}, ship_data)
                            }
                            # Reset Key to clear form
                            st.session_state.billing_key = str(random.randint(1000, 9999))
                            del st.session_state.grid_df
                            st.rerun()

        # --- SUCCESS BUTTONS (Outside loop) ---
        if st.session_state.last_generated_invoice:
            last = st.session_state.last_generated_invoice
            st.success(f"✅ Invoice {last['no']} Saved!")
            
            b1, b2, b3 = st.columns(3)
            b1.download_button("⬇️ PDF", last['pdf_bytes'], f"Inv_{last['no']}.pdf", "application/pdf", use_container_width=True)
            if last['wa_link']: b2.link_button("📱 WhatsApp", last['wa_link'], use_container_width=True)
            else: b2.button("📱 WhatsApp", disabled=True, use_container_width=True)
            b3.button("📧 Email", disabled=True, use_container_width=True) # Placeholder

    # ... (Other menus: Customer Master, Profile etc. remain as previously fixed) ...

# (Login logic remains same)
if st.session_state.user_id: main_app()
else: login_page()
