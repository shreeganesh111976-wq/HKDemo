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

# --- EMAIL CONFIGURATION ---
SENDER_EMAIL = "your_email@gmail.com"  # <--- REPLACE THIS
SENDER_PASSWORD = "xxxx xxxx xxxx xxxx"  # <--- REPLACE THIS

# --- CONSTANTS ---
APP_NAME = "HisaabKeeper"

# --- GOOGLE SHEETS CONNECTION HANDLER ---
def get_db_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def fetch_data(worksheet_name):
    """Fetches data and enforces schema."""
    conn = get_db_connection()
    schema = {
        "Users": [
            "UserID", "Username", "Password", "Business Name", "Tagline", "Is GST", "GSTIN", "PAN",
            "Mobile", "Email", "Template", 
            "Addr1", "Addr2", "Pincode", "District", "State", 
            "Bank Name", "Branch", "Account No", "IFSC", "UPI"
        ],
        "Customers": [
            "UserID", "Name", "GSTIN", 
            "Address 1", "Address 2", "Address 3", "State", 
            "Mobile", "Email"
        ],
        "Invoices": [
            "UserID", "Bill No", "Date", "Buyer Name", "Items", 
            "Total Taxable", "CGST", "SGST", "IGST", "Grand Total", 
            "Ship Name", "Ship GSTIN", "Ship Addr1", "Ship Addr2", "Ship Addr3"
        ],
        "Receipts": ["UserID", "Date", "Party Name", "Amount", "Note"],
        "Inward": ["UserID", "Date", "Supplier Name", "Total Value"]
    }
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
        if worksheet_name in schema:
            expected_cols = schema[worksheet_name]
            for col in expected_cols:
                if col not in df.columns: df[col] = ""
            df = df[expected_cols]
        return df
    except Exception:
        cols = schema.get(worksheet_name, [])
        return pd.DataFrame(columns=cols)

def fetch_user_data(worksheet_name):
    if not st.session_state.get("user_id"): return pd.DataFrame()
    df = fetch_data(worksheet_name)
    if "UserID" in df.columns:
        df["UserID"] = df["UserID"].astype(str)
        return df[df["UserID"] == str(st.session_state["user_id"])]
    return df

def save_row_to_sheet(worksheet_name, new_row_dict):
    conn = get_db_connection()
    df = fetch_data(worksheet_name)
    if "UserID" not in new_row_dict and worksheet_name != "Users":
        new_row_dict["UserID"] = st.session_state["user_id"]
    new_df = pd.DataFrame([new_row_dict])
    if df.empty: updated_df = new_df
    else: updated_df = pd.concat([df, new_df], ignore_index=True)
    try:
        conn.update(worksheet=worksheet_name, data=updated_df)
        st.cache_data.clear()
    except Exception as e: st.error(f"Error saving to database: {e}")

def save_bulk_data(worksheet_name, new_df_chunk):
    conn = get_db_connection()
    df = fetch_data(worksheet_name)
    if "UserID" not in new_df_chunk.columns:
        new_df_chunk["UserID"] = st.session_state["user_id"]
    else:
        new_df_chunk["UserID"] = new_df_chunk["UserID"].fillna(st.session_state["user_id"])
    if df.empty: updated_df = new_df_chunk
    else: updated_df = pd.concat([df, new_df_chunk], ignore_index=True)
    try:
        conn.update(worksheet=worksheet_name, data=updated_df)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error saving bulk data: {e}")
        return False

def update_user_profile(updated_profile_dict):
    conn = get_db_connection()
    df = fetch_data("Users")
    df["UserID"] = df["UserID"].astype(str)
    current_uid = str(st.session_state["user_id"])
    idx = df[df["UserID"] == current_uid].index
    if not idx.empty:
        for key, value in updated_profile_dict.items():
            df.at[idx[0], key] = value
        try:
            conn.update(worksheet="Users", data=df)
            st.cache_data.clear()
            st.session_state.user_profile = df.iloc[idx[0]].to_dict()
            return True
        except Exception as e:
            st.error(f"Failed to update profile: {e}")
            return False
    return False

# --- PDF GENERATOR ---
def generate_pdf_buffer(seller, buyer, items, inv_no, inv_date, totals, ship_details=None):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w/2, h-50, str(seller.get('Business Name', 'My Firm')))
    c.setFont("Helvetica", 10)
    c.drawCentredString(w/2, h-65, str(seller.get('Tagline', '')))
    y = h-80
    if seller.get('Is GST') == 'Yes' and seller.get('GSTIN'): 
        c.drawCentredString(w/2, y, f"GSTIN: {seller.get('GSTIN')}"); y-=12
    elif seller.get('PAN'):
        c.drawCentredString(w/2, y, f"PAN: {seller.get('PAN')}"); y-=12
    addr = f"{seller.get('Addr1','')}, {seller.get('Addr2','')}, {seller.get('State','')}"
    c.drawCentredString(w/2, y, addr); y-=12
    c.drawCentredString(w/2, y, f"M: {seller.get('Mobile','')} | E: {seller.get('Email','')}")
    c.line(30, y-10, w-30, y-10)
    
    y_bill = y-40
    c.setFont("Helvetica-Bold", 10); c.drawString(40, y_bill, "Bill To:")
    c.setFont("Helvetica", 10)
    c.drawString(40, y_bill-15, str(buyer.get('Name','')))
    c.drawString(40, y_bill-30, f"GSTIN: {buyer.get('GSTIN','')}")
    c.drawString(40, y_bill-45, f"Addr: {buyer.get('Address 1','')}, {buyer.get('State','')}")

    if ship_details and ship_details.get("IsShipping"):
        c.setFont("Helvetica-Bold", 10); c.drawString(200, y_bill, "Ship To:")
        c.setFont("Helvetica", 10)
        c.drawString(200, y_bill-15, str(ship_details.get('Name','')))
        c.drawString(200, y_bill-30, f"GSTIN: {ship_details.get('GSTIN','')}")
        c.drawString(200, y_bill-45, f"Addr: {ship_details.get('Addr1','')}")

    c.setFont("Helvetica-Bold", 10); c.drawString(400, y_bill, "Invoice Details:")
    c.setFont("Helvetica", 10)
    c.drawString(400, y_bill-15, f"No: {inv_no}")
    c.drawString(400, y_bill-30, f"Date: {inv_date}")
    
    y_table = y_bill - 70
    c.setFont("Helvetica-Bold", 9)
    headers = ["Item", "HSN", "Qty", "UOM", "Rate", "GST%", "Total"]
    x_positions = [40, 200, 250, 300, 350, 400, 450]
    for i, h_text in enumerate(headers): c.drawString(x_positions[i], y_table, h_text)
    c.line(30, y_table-5, w-30, y_table-5)
    
    y_row = y_table - 20
    c.setFont("Helvetica", 9)
    for i in items:
        name = str(i.get('Description', 'Item'))[:25]
        hsn = str(i.get('HSN', ''))
        qty = str(i.get('Qty', 0))
        uom = str(i.get('UOM', ''))
        rate = f"{float(i.get('Rate', 0)):.2f}"
        gst_rate = f"{float(i.get('GST Rate', 0))}%"
        base = float(i.get('Qty', 0)) * float(i.get('Rate', 0))
        tax_amt = base * (float(i.get('GST Rate', 0))/100)
        total_row = base + tax_amt
        
        c.drawString(40, y_row, name)
        c.drawString(200, y_row, hsn)
        c.drawString(250, y_row, qty)
        c.drawString(300, y_row, uom)
        c.drawString(350, y_row, rate)
        c.drawString(400, y_row, gst_rate)
        c.drawString(450, y_row, f"{total_row:.2f}")
        y_row -= 15
        if y_row < 50: c.showPage(); y_row = h - 50

    c.line(30, y_row+5, w-30, y_row+5)
    c.setFont("Helvetica-Bold", 10)
    y_total = y_row - 20
    c.drawRightString(500, y_total, f"Taxable Value: {totals['taxable']:.2f}"); y_total -= 15
    if totals['cgst'] > 0:
        c.drawRightString(500, y_total, f"CGST: {totals['cgst']:.2f}"); y_total -= 15
        c.drawRightString(500, y_total, f"SGST: {totals['sgst']:.2f}"); y_total -= 15
    if totals['igst'] > 0:
        c.drawRightString(500, y_total, f"IGST: {totals['igst']:.2f}"); y_total -= 15
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(500, y_total-10, f"Grand Total: ₹ {totals['total']:.2f}")
    
    if seller.get("Bank Name") and str(seller.get("Bank Name")) != "nan":
        y_bank = 100
        c.line(30, y_bank + 15, w-30, y_bank + 15)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(40, y_bank, "Bank Details:")
        c.setFont("Helvetica", 9)
        c.drawString(110, y_bank, f"{seller.get('Bank Name','')} | A/c: {seller.get('Account No','')} | IFSC: {seller.get('IFSC','')}")
    c.save()
    buffer.seek(0)
    return buffer

def get_whatsapp_web_link(mobile, msg):
    if not mobile: return None
    clean_num = re.sub(r'\D', '', str(mobile)) # Remove non-digits
    if not clean_num.startswith("91") and len(clean_num) == 10:
        clean_num = "91" + clean_num # Add 91 if missing
    return f"https://web.whatsapp.com/send?phone={clean_num}&text={urllib.parse.quote(msg)}"

def generate_unique_id(): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
def is_valid_email(email): return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None
def is_valid_mobile(mobile): return re.match(r'^[6-9]\d{9}$', mobile) is not None
def is_valid_pan(pan): return re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', pan) is not None
def is_valid_gstin(gstin): return re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$', gstin) is not None

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

# --- SESSION STATE ---
if "user_id" not in st.session_state: st.session_state.user_id = None
if "user_profile" not in st.session_state: st.session_state.user_profile = {}
if "auth_mode" not in st.session_state: st.session_state.auth_mode = "login"
if "reg_success_msg" not in st.session_state: st.session_state.reg_success_msg = None
if "otp_generated" not in st.session_state: st.session_state.otp_generated = None
if "otp_email" not in st.session_state: st.session_state.otp_email = None
if "reg_temp_data" not in st.session_state: st.session_state.reg_temp_data = {}
if "last_generated_invoice" not in st.session_state: st.session_state.last_generated_invoice = None
# Reset trigger for invoice clear
if "reset_invoice_trigger" not in st.session_state: st.session_state.reset_invoice_trigger = False

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

def main_app():
    raw_profile = st.session_state.user_profile
    profile = {k: (v if str(v) != 'nan' else '') for k, v in raw_profile.items()}
    st.sidebar.title(f"🏢 {profile.get('Business Name', 'My Business')}")
    st.sidebar.caption(f"User: {profile.get('Username', 'User')}")
    if st.sidebar.button("Logout"):
        st.session_state.user_id = None; st.session_state.user_profile = {}; st.session_state.auth_mode = "login"; st.rerun()
    
    choice = st.sidebar.radio("Menu", ["Dashboard", "Customer Master", "Billing Master", "Ledger", "Inward", "Company Profile"])
    
    if choice == "Dashboard":
        st.header("📊 Dashboard")
        df_inv = fetch_user_data("Invoices")
        total_sales = 0
        if not df_inv.empty and "Grand Total" in df_inv.columns: 
            total_sales = pd.to_numeric(df_inv["Grand Total"], errors='coerce').sum()
        st.metric("Total Sales", f"₹ {total_sales:,.0f}")
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
                    save_row_to_sheet("Customers", {
                        "Name": c_name, "GSTIN": c_gst, "Address 1": addr1, "Address 2": addr2, "Address 3": addr3, "State": state_val, "Mobile": mob, "Email": email
                    })
                    st.success("Customer Saved Successfully!"); time.sleep(1); st.rerun()

        with st.expander("📋 Customer Database", expanded=False):
            view_df = fetch_user_data("Customers")
            if not view_df.empty: st.dataframe(view_df[cust_cols], use_container_width=True)
            else: st.info("No customers found.")

    elif choice == "Billing Master":
        st.header("🧾 New Invoice")
        df_cust = fetch_user_data("Customers")
        
        # --- UI LAYOUT FIXED: MATCHING FONT SIZES & BOLD ---
        c1, c2, c3 = st.columns([2.5, 0.5, 1])
        
        # 1. Customer Label (HTML for styling)
        c1.markdown("<p style='font-size:14px; font-weight:bold; margin-bottom:-10px;'>👤 Select Customer</p>", unsafe_allow_html=True)
        cust_list = ["Select"] + df_cust["Name"].tolist() if not df_cust.empty else ["Select"]
        sel_cust_name = c1.selectbox("Select Customer", cust_list, label_visibility="collapsed")
        
        c2.write(""); c2.write("")
        if c2.button("➕", type="primary", help="Add New Customer"): st.toast("Go to 'Customer Master' to add.", icon="ℹ️")

        # 3. Date Label (HTML for styling)
        c3.markdown("<p style='font-size:14px; font-weight:bold; margin-bottom:-10px;'>📅 Invoice Date</p>", unsafe_allow_html=True)
        inv_date_obj = c3.date_input("Invoice Date", format="DD/MM/YYYY", label_visibility="collapsed") 
        inv_date_str = inv_date_obj.strftime("%d/%m/%Y")
        
        cust_state = ""; cust_gstin = ""; cust_mob = ""; cust_email = ""
        if sel_cust_name != "Select" and not df_cust.empty:
            cust_row = df_cust[df_cust["Name"] == sel_cust_name].iloc[0]
            cust_gstin = str(cust_row.get("GSTIN", "")); cust_state = str(cust_row.get("State", ""))
            cust_mob = str(cust_row.get("Mobile", "")); cust_email = str(cust_row.get("Email", ""))
            c_info_addr = f"{cust_row.get('Address 1','')}, {cust_row.get('Address 2','')}"
            st.info(f"**GSTIN:** {cust_gstin if cust_gstin else 'Unregistered'} | **Mobile:** {cust_mob} | **Addr:** {c_info_addr}")

        st.write("")
        is_ship_diff = st.checkbox("🚢 Shipping Details")
        ship_data = {}
        if is_ship_diff:
            with st.container(border=True):
                sc1, sc2 = st.columns(2)
                ship_name = sc1.text_input("Ship Name"); ship_gst = sc2.text_input("Ship GSTIN")
                ship_a1 = st.text_input("Ship Address 1"); ship_a2 = st.text_input("Ship Address 2"); ship_a3 = st.text_input("Ship Address 3")
                ship_data = {"IsShipping": True, "Name": ship_name, "GSTIN": ship_gst, "Addr1": ship_a1, "Addr2": ship_a2, "Addr3": ship_a3}

        st.write("")
        # Invoice Label (Matching Others)
        st.markdown("<p style='font-size:14px; font-weight:bold; margin-bottom:-10px;'>🧾 Invoice Number</p>", unsafe_allow_html=True)
        ic1, ic2 = st.columns([1.3, 3]) 
        inv_no = ic1.text_input("Invoice Number", label_visibility="collapsed", placeholder="Enter Inv No")
        df_inv_past = fetch_user_data("Invoices")
        past_str = "No past invoices"
        if not df_inv_past.empty:
            past_nos = df_inv_past["Bill No"].tail(3).tolist()
            past_str = ", ".join(map(str, past_nos))
        st.caption(f"📜 Last 3: {past_str}")

        st.divider()
        st.markdown("#### 📦 Product / Service Details") # Reduced Header Size

        # --- AUTO CLEAR LOGIC ---
        if st.session_state.reset_invoice_trigger:
            st.session_state.invoice_items_grid = pd.DataFrame([{"Description": "", "HSN": "", "Qty": 1.0, "UOM": "PCS", "Rate": 0.0, "GST Rate": 0.0}])
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
            }, key="final_invoice_editor_polished"
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

        # --- UI LAYOUT: RIGHT ALIGNED TOTALS & SAVE BUTTON ---
        st.write("")
        c_spacer, c_totals = st.columns([1.5, 1])
        
        with c_totals:
            # Custom HTML for Clean Invoice Footer Look
            total_html = f"""
            <div style="text-align: right; font-family: sans-serif;">
                <p style="font-size: 16px; margin: 5px 0;">Sub Total: <span style="float: right; font-weight: bold;">₹ {total_taxable:,.2f}</span></p>
            """
            if is_inter_state:
                total_html += f'<p style="font-size: 16px; margin: 5px 0;">IGST: <span style="float: right; font-weight: bold;">₹ {igst_val:,.2f}</span></p>'
            else:
                total_html += f'<p style="font-size: 16px; margin: 5px 0;">CGST+SGST: <span style="float: right; font-weight: bold;">₹ {cgst_val+sgst_val:,.2f}</span></p>'
            
            total_html += f"""
                <hr style="margin: 10px 0;">
                <p style="font-size: 20px; font-weight: bold; margin: 5px 0;">Total: <span style="float: right;">₹ {grand_total:,.2f}</span></p>
            </div>
            """
            st.markdown(total_html, unsafe_allow_html=True)
            
            st.write("")
            # GENERATE BUTTON (Right Aligned via Column)
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
                    save_row_to_sheet("Invoices", db_row)
                    
                    # Msg Gen
                    firm_name = profile.get('Business Name', 'Our Firm')
                    contact = f"{profile.get('Mobile','')}"
                    msg_body = f"""Hi *{sel_cust_name}*,

Greetings from *{firm_name}*. I’m sending over the invoice *{inv_no}* dated *{inv_date_str}* for *₹{grand_total:,.2f}*. The details are included in the attachment for your review.

Thanks again for your cooperation and continued support.

*{firm_name}*
{contact}

------------------------------------------
This mail is autogenerated through the *HisaabKeeper! Billing Software*.

To get demo or Free trial connect us on hello.hisaabkeeper@gmail.com or whatsapp us on +91 6353953790"""
                    
                    # Store Success State
                    st.session_state.last_generated_invoice = {
                        "no": inv_no, "pdf_bytes": generate_pdf_buffer(profile, df_cust[df_cust["Name"] == sel_cust_name].iloc[0].to_dict(), valid_items.to_dict('records'), inv_no, inv_date_str, {'taxable': total_taxable, 'cgst': cgst_val, 'sgst': sgst_val, 'igst': igst_val, 'total': grand_total}, ship_data),
                        "wa_link": get_whatsapp_web_link(cust_mob, msg_body) if cust_mob else None,
                        "mail_link": f"mailto:{cust_email}?subject={urllib.parse.quote(f'Invoice {inv_no} from {firm_name}')}&body={urllib.parse.quote(msg_body)}" if cust_email else None
                    }
                    # Trigger Reset
                    st.session_state.reset_invoice_trigger = True
                    st.rerun()

        # --- SUCCESS ACTIONS (HIDDEN UNTIL GENERATED) ---
        if st.session_state.last_generated_invoice:
            last_inv = st.session_state.last_generated_invoice
            st.success(f"✅ Invoice {last_inv['no']} Generated Successfully!")
            
            ac1, ac2, ac3 = st.columns(3)
            ac1.download_button("⬇️ Download PDF", last_inv["pdf_bytes"], f"Invoice_{last_inv['no']}.pdf", "application/pdf", use_container_width=True)
            
            if last_inv["wa_link"]: ac2.link_button("📱 WhatsApp Web", last_inv["wa_link"], use_container_width=True)
            else: ac2.button("📱 WhatsApp", disabled=True, use_container_width=True, help="No Mobile Number")
            
            if last_inv["mail_link"]: ac3.link_button("📧 Email", last_inv["mail_link"], use_container_width=True)
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
            st.metric("Pending Balance", f"₹ {total_billed - total_paid:,.2f}")
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
                c3, c4 = st.columns(2)
                logo = c3.file_uploader("Upload Company Logo (PNG/JPG)", type=['png', 'jpg'])
                template = c4.selectbox("PDF Template", ["Simple", "Modern", "Formal"], index=["Simple", "Modern", "Formal"].index(profile.get("Template", "Simple")))
                c5, c6 = st.columns(2)
                mob = c5.text_input("Business Mobile", value=profile.get("Mobile", ""))
                em = c6.text_input("Business Email", value=profile.get("Email", ""))
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
                acc_no = bc3.text_input("Account Number (Numeric Only)", value=profile.get("Account No", ""))
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
                if acc_no and not acc_no.isdigit(): errors.append("Account Number must contain only digits.")
                if upi and "@" not in upi: errors.append("Invalid UPI ID (must contain '@').")
                if errors:
                    for e in errors: st.error(e)
                else:
                    updated_data = {
                        "Business Name": bn, "Tagline": tag, "Mobile": mob, "Email": em, "Template": template,
                        "Is GST": gst_selection, "GSTIN": final_gstin, "PAN": final_pan,
                        "Addr1": a1, "Addr2": a2, "Pincode": pincode, "District": dist, "State": state,
                        "Bank Name": bank_name, "Branch": branch, "Account No": acc_no, "IFSC": ifsc, "UPI": upi
                    }
                    if update_user_profile(updated_data): st.success("Profile Updated Successfully!"); time.sleep(1); st.rerun()

if st.session_state.user_id: main_app()
else: login_page()
