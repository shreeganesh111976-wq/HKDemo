import streamlit as st
import pandas as pd
import json
import time
import io
import urllib.parse
import random
import string
import re  # Added for Regex Validation
from datetime import date
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.lib.units import inch
from streamlit_gsheets import GSheetsConnection

# --- PAGE CONFIG ---
st.set_page_config(page_title="HisaabKeeper Cloud", layout="wide", page_icon="🧾")

# --- SECRETS & CONSTANTS ---
APP_NAME = "HisaabKeeper"

# --- GOOGLE SHEETS CONNECTION HANDLER ---
def get_db_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def fetch_data(worksheet_name):
    """Fetches data from a worksheet with error handling."""
    conn = get_db_connection()
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
        return df
    except Exception:
        # Default columns if sheet is empty/missing
        if worksheet_name == "Users": 
            cols = ["UserID", "Username", "Password", "Business Name", "Tagline", "Is GST", "GSTIN", "Mobile", "Email", "Addr1", "Addr2"]
        elif worksheet_name == "Customers": 
            cols = ["UserID", "Name", "GSTIN", "Mobile", "Address 1"]
        elif worksheet_name == "Invoices": 
            cols = ["UserID", "Bill No", "Date", "Buyer Name", "Invoice Value", "Taxable", "Items"]
        elif worksheet_name == "Receipts": 
            cols = ["UserID", "Date", "Party Name", "Amount", "Note"]
        elif worksheet_name == "Inward": 
            cols = ["UserID", "Date", "Supplier Name", "Total Value"]
        else: 
            cols = []
        return pd.DataFrame(columns=cols)

def fetch_user_data(worksheet_name):
    """Fetches data ONLY for the logged-in user."""
    if not st.session_state.get("user_id"): return pd.DataFrame()
    df = fetch_data(worksheet_name)
    
    if "UserID" in df.columns:
        df["UserID"] = df["UserID"].astype(str)
        return df[df["UserID"] == str(st.session_state["user_id"])]
    return df

def save_row_to_sheet(worksheet_name, new_row_dict):
    """Appends a single row to the sheet."""
    conn = get_db_connection()
    df = fetch_data(worksheet_name)
    
    if "UserID" not in new_row_dict and worksheet_name != "Users":
        new_row_dict["UserID"] = st.session_state["user_id"]
    
    new_df = pd.DataFrame([new_row_dict])
    
    if df.empty:
        updated_df = new_df
    else:
        updated_df = pd.concat([df, new_df], ignore_index=True)
    
    try:
        conn.update(worksheet=worksheet_name, data=updated_df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Error saving to database: {e}")

def update_user_profile(updated_profile_dict):
    """Updates the existing user's profile row in the Users sheet."""
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
def generate_pdf_buffer(seller, buyer, items, inv_no, totals):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w/2, h-50, str(seller.get('Business Name', 'My Firm')))
    c.setFont("Helvetica", 10)
    c.drawCentredString(w/2, h-65, str(seller.get('Tagline', '')))
    
    y = h-80
    if seller.get('GSTIN'): c.drawCentredString(w/2, y, f"GSTIN: {seller.get('GSTIN')}"); y-=12
    addr = f"{seller.get('Addr1','')}, {seller.get('Addr2','')}"
    c.drawCentredString(w/2, y, addr); y-=12
    c.drawCentredString(w/2, y, f"M: {seller.get('Mobile','')} | E: {seller.get('Email','')}")
    
    c.line(30, y-10, w-30, y-10)
    
    y_bill = y-40
    c.setFont("Helvetica-Bold", 10); c.drawString(40, y_bill, "Bill To:")
    c.setFont("Helvetica", 10)
    c.drawString(40, y_bill-15, str(buyer.get('Name','')))
    c.drawString(40, y_bill-30, f"GSTIN: {buyer.get('GSTIN','')}")
    c.drawString(40, y_bill-45, f"Addr: {buyer.get('Address 1','')}")

    c.setFont("Helvetica-Bold", 10); c.drawString(400, y_bill, "Invoice Details:")
    c.setFont("Helvetica", 10)
    c.drawString(400, y_bill-15, f"No: {inv_no}")
    c.drawString(400, y_bill-30, f"Date: {buyer.get('Date','')}")
    
    y_table = y_bill - 70
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y_table, "Item"); c.drawString(300, y_table, "Qty"); c.drawString(350, y_table, "Rate"); c.drawString(450, y_table, "Amount")
    c.line(30, y_table-5, w-30, y_table-5)
    
    y_row = y_table - 20
    c.setFont("Helvetica", 9)
    for i in items:
        name = str(i.get('Description', 'Item'))
        qty = str(i.get('Qty', 0))
        rate = f"{float(i.get('Rate', 0)):.2f}"
        amt = f"{float(i.get('Qty', 0)) * float(i.get('Rate', 0)):.2f}"
        c.drawString(40, y_row, name); c.drawString(300, y_row, qty); c.drawString(350, y_row, rate); c.drawString(450, y_row, amt)
        y_row -= 15
        if y_row < 50: c.showPage(); y_row = h - 50

    c.line(30, y_row+5, w-30, y_row+5)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(500, y_row-20, f"Taxable: {totals['taxable']:.2f}")
    c.drawRightString(500, y_row-35, f"Total: {totals['total']:.2f}")
    c.save()
    buffer.seek(0)
    return buffer

def get_whatsapp_link(mobile, msg):
    if not mobile: return None
    return f"https://wa.me/91{mobile}?text={urllib.parse.quote(msg)}"

# --- AUTHENTICATION & VALIDATION HELPERS ---
if "user_id" not in st.session_state: st.session_state.user_id = None
if "user_profile" not in st.session_state: st.session_state.user_profile = {}
if "auth_mode" not in st.session_state: st.session_state.auth_mode = "login"
if "reg_success_msg" not in st.session_state: st.session_state.reg_success_msg = None

def generate_unique_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def is_valid_email(email):
    # Standard email regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_mobile(mobile):
    # Checks if 10 digits and starts with 6,7,8,9
    pattern = r'^[6-9]\d{9}$'
    return re.match(pattern, mobile) is not None

def login_page():
    st.markdown("<h1 style='text-align:center;'>🔐 HisaabKeeper Login</h1>", unsafe_allow_html=True)
    
    if st.session_state.reg_success_msg:
        st.success(st.session_state.reg_success_msg)
        st.session_state.reg_success_msg = None

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
                    else: st.error("System Error: Users database is missing columns.")

            st.markdown("---")
            col1, col2 = st.columns([0.7, 0.3])
            col1.write("New to HisaabKeeper?")
            if col2.button("Create Account"):
                st.session_state.auth_mode = "register"
                st.rerun()

    elif st.session_state.auth_mode == "register":
        with st.container():
            st.subheader("Create New Account")
            with st.form("reg_form"):
                new_username = st.text_input("Choose Username (Unique)")
                new_pwd = st.text_input("Choose Password", type="password")
                bn = st.text_input("Business Name")
                mob = st.text_input("Mobile Number (10 digits)")
                em = st.text_input("Email ID")
                
                submitted = st.form_submit_button("Register")
                
                if submitted:
                    df_users = fetch_data("Users")
                    
                    # --- VALIDATION CHECKS ---
                    if not new_username or not new_pwd or not bn or not mob or not em:
                        st.error("All fields are mandatory.")
                    elif not is_valid_mobile(mob):
                        st.error("Invalid Mobile Number! Enter 10 digits starting with 6-9.")
                    elif not is_valid_email(em):
                        st.error("Invalid Email ID format!")
                    elif not df_users.empty and "Username" in df_users.columns and new_username in df_users["Username"].astype(str).values:
                        st.error("Username already taken! Please choose another.")
                    else:
                        unique_id = generate_unique_id()
                        new_user = {
                            "UserID": unique_id, "Username": new_username, "Password": new_pwd, 
                            "Business Name": bn, "Tagline": "", "GSTIN": "", 
                            "Mobile": mob, "Email": em, "Addr1": "", "Addr2": "", "Is GST": "No"
                        }
                        save_row_to_sheet("Users", new_user)
                        st.session_state.reg_success_msg = f"🎉 Congratulations! Registration Successful. Please login with: {new_username}"
                        st.session_state.auth_mode = "login"
                        st.rerun()

            st.markdown("---")
            if st.button("Back to Login"):
                st.session_state.auth_mode = "login"
                st.rerun()

# --- MAIN APP ---
def main_app():
    profile = st.session_state.user_profile
    st.sidebar.title(f"🏢 {profile.get('Business Name', 'My Business')}")
    st.sidebar.caption(f"User: {profile.get('Username', 'User')}")
    
    if st.sidebar.button("Logout"):
        st.session_state.user_id = None
        st.session_state.user_profile = {}
        st.session_state.auth_mode = "login"
        st.rerun()
    
    choice = st.sidebar.radio("Menu", ["Dashboard", "Customer Master", "Billing", "Ledger", "Inward", "Profile"])
    
    if choice == "Dashboard":
        st.header("📊 Dashboard")
        df_inv = fetch_user_data("Invoices")
        total_sales = 0
        if not df_inv.empty and "Invoice Value" in df_inv.columns:
            total_sales = pd.to_numeric(df_inv["Invoice Value"], errors='coerce').sum()
        st.metric("Total Sales", f"₹ {total_sales:,.0f}")
        st.dataframe(df_inv.tail(5), use_container_width=True)

    elif choice == "Customer Master":
        st.header("👥 Customers")
        with st.expander("Add New Customer"):
            with st.form("add_c"):
                name = st.text_input("Name"); gst = st.text_input("GSTIN"); mob = st.text_input("Mobile"); addr = st.text_input("Address")
                if st.form_submit_button("Save"):
                    save_row_to_sheet("Customers", {"Name": name, "GSTIN": gst, "Mobile": mob, "Address 1": addr})
                    st.success("Saved!"); st.rerun()
        st.dataframe(fetch_user_data("Customers"), use_container_width=True)

    elif choice == "Billing":
        st.header("🧾 New Invoice")
        df_cust = fetch_user_data("Customers")
        cust_list = ["Select"] + df_cust["Name"].tolist() if not df_cust.empty else ["Select"]
        
        c1, c2 = st.columns([2,1])
        sel_cust = c1.selectbox("Customer", cust_list)
        inv_date = c2.date_input("Date")
        inv_no = st.text_input("Invoice No (e.g. 001)")
        
        if "items" not in st.session_state or not isinstance(st.session_state.items, pd.DataFrame):
            st.session_state.items = pd.DataFrame([{"Description": "", "Qty": 1.0, "Rate": 0.0}])
        try:
            st.session_state.items["Description"] = st.session_state.items["Description"].astype(str)
            st.session_state.items["Qty"] = st.session_state.items["Qty"].astype(float)
            st.session_state.items["Rate"] = st.session_state.items["Rate"].astype(float)
        except Exception:
            st.session_state.items = pd.DataFrame([{"Description": "", "Qty": 1.0, "Rate": 0.0}])

        edited_items = st.data_editor(
            st.session_state.items, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "Description": st.column_config.TextColumn("Description", required=True),
                "Qty": st.column_config.NumberColumn("Qty", required=True, default=1.0),
                "Rate": st.column_config.NumberColumn("Rate", required=True, default=0.0)
            },
            key="bill_editor_safe"
        )
        
        valid = edited_items[edited_items["Description"]!=""].copy()
        valid["Qty"] = pd.to_numeric(valid["Qty"], errors='coerce').fillna(0)
        valid["Rate"] = pd.to_numeric(valid["Rate"], errors='coerce').fillna(0)
        valid["Amount"] = valid["Qty"] * valid["Rate"]
        subtotal = valid["Amount"].sum()
        is_gst = profile.get("Is GST", "No") == "Yes"
        tax = subtotal * 0.18 if is_gst else 0
        total = subtotal + tax
        st.markdown(f"### Total: ₹ {total:,.2f}")
        
        if st.button("Generate & Save", type="primary"):
            if sel_cust == "Select": st.error("Select Customer")
            else:
                items_json = json.dumps(valid.to_dict('records'))
                save_row_to_sheet("Invoices", {"Bill No": inv_no, "Date": str(inv_date), "Buyer Name": sel_cust, "Invoice Value": total, "Taxable": subtotal, "Items": items_json})
                st.success("Invoice Saved!")
                cust_data = df_cust[df_cust["Name"] == sel_cust].iloc[0].to_dict()
                pdf_bytes = generate_pdf_buffer(profile, cust_data, valid.to_dict('records'), inv_no, {'taxable': subtotal, 'total': total})
                st.download_button("⬇️ Download PDF", pdf_bytes, f"Inv_{inv_no}.pdf", "application/pdf")

    elif choice == "Ledger":
        st.header("📒 Ledger")
        df_cust = fetch_user_data("Customers")
        sel_cust = st.selectbox("Customer", ["Select"] + df_cust["Name"].tolist())
        if sel_cust != "Select":
            df_inv = fetch_user_data("Invoices")
            df_rec = fetch_user_data("Receipts")
            total_billed = 0; total_paid = 0
            if not df_inv.empty and "Invoice Value" in df_inv.columns:
                total_billed = pd.to_numeric(df_inv[df_inv["Buyer Name"] == sel_cust]["Invoice Value"], errors='coerce').sum()
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

    elif choice == "Profile":
        st.header("⚙️ Company Profile")
        st.info(f"🔒 System User ID: {st.session_state.user_id} (16-Digit Unique Code)")
        with st.form("edit_profile"):
            c1, c2 = st.columns(2)
            bn = st.text_input("Business Name", value=profile.get("Business Name", ""))
            tag = st.text_input("Tagline", value=profile.get("Tagline", ""))
            c3, c4 = st.columns(2)
            gstin = st.text_input("GSTIN", value=profile.get("GSTIN", ""))
            is_gst = st.selectbox("Registered GST?", ["Yes", "No"], index=0 if profile.get("Is GST") == "Yes" else 1)
            c5, c6 = st.columns(2)
            mob = st.text_input("Mobile", value=profile.get("Mobile", ""))
            em = st.text_input("Email", value=profile.get("Email", ""))
            addr1 = st.text_input("Address 1", value=profile.get("Addr1", ""))
            addr2 = st.text_input("Address 2", value=profile.get("Addr2", ""))
            if st.form_submit_button("💾 Update Profile"):
                updated_data = {"Business Name": bn, "Tagline": tag, "GSTIN": gstin, "Is GST": is_gst, "Mobile": mob, "Email": em, "Addr1": addr1, "Addr2": addr2}
                if update_user_profile(updated_data):
                    st.success("Profile Updated!"); time.sleep(1); st.rerun()

if st.session_state.user_id: main_app()
else: login_page()
