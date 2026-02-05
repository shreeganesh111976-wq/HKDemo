import streamlit as st
import pandas as pd
import json
import time
import io
import urllib.parse
import smtplib
import ssl
import re
import os
from datetime import date, datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
import altair as alt
from streamlit_gsheets import GSheetsConnection
from email.message import EmailMessage

# --- PAGE CONFIG ---
st.set_page_config(page_title="HisaabKeeper Multi-User", layout="wide", page_icon="🧾")

# --- CONSTANTS ---
APP_NAME = "HisaabKeeper"
HARD_STOP_DATE = date(2026, 6, 30)
STATE_CODES = {
    '01': 'Jammu & Kashmir', '02': 'Himachal Pradesh', '03': 'Punjab', '04': 'Chandigarh', '24': 'Gujarat', '27': 'Maharashtra', '07': 'Delhi', '08': 'Rajasthan', '09': 'Uttar Pradesh', '29': 'Karnataka', '33': 'Tamil Nadu', '36': 'Telangana'
}

# --- GOOGLE SHEETS CONNECTION HANDLER ---
# This function handles reading/writing to ensure data isolation
def get_db_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def fetch_data(worksheet_name):
    """Fetches all data from a worksheet."""
    conn = get_db_connection()
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0) # ttl=0 ensures fresh data
        return df
    except Exception as e:
        # Return empty DF with correct columns if sheet is empty/missing
        if worksheet_name == "Users": cols = ["UserID", "Password", "Business Name"]
        elif worksheet_name == "Customers": cols = ["UserID", "Name", "Mobile"]
        elif worksheet_name == "Invoices": cols = ["UserID", "Bill No", "Invoice Value"]
        elif worksheet_name == "Receipts": cols = ["UserID", "Amount"]
        elif worksheet_name == "Inward": cols = ["UserID", "Total Value"]
        else: cols = []
        return pd.DataFrame(columns=cols)

def fetch_user_data(worksheet_name):
    """Fetches data ONLY for the logged-in user."""
    if not st.session_state.get("user_id"): return pd.DataFrame()
    df = fetch_data(worksheet_name)
    # Filter by UserID
    if "UserID" in df.columns:
        return df[df["UserID"] == st.session_state["user_id"]]
    return df

def save_row_to_sheet(worksheet_name, new_row_dict):
    """Appends a single row to the sheet."""
    conn = get_db_connection()
    df = fetch_data(worksheet_name)
    
    # Ensure UserID is attached
    if "UserID" not in new_row_dict and worksheet_name != "Users":
        new_row_dict["UserID"] = st.session_state["user_id"]
        
    new_df = pd.DataFrame([new_row_dict])
    updated_df = pd.concat([df, new_df], ignore_index=True)
    
    # Update Google Sheet
    conn.update(worksheet=worksheet_name, data=updated_df)
    # Clear cache
    st.cache_data.clear()

# --- PDF GENERATOR (Kept Lightweight) ---
def generate_pdf_buffer(seller, buyer, items, inv_no, totals):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    
    # Header
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w/2, h-50, seller.get('Business Name', 'My Firm'))
    c.setFont("Helvetica", 10)
    c.drawCentredString(w/2, h-65, seller.get('Tagline', ''))
    
    # Seller Details
    c.setFont("Helvetica", 9)
    y = h-80
    if seller.get('GSTIN'): c.drawCentredString(w/2, y, f"GSTIN: {seller.get('GSTIN')}"); y-=12
    c.drawCentredString(w/2, y, f"{seller.get('Addr1','')}, {seller.get('Addr2','')}"); y-=12
    c.drawCentredString(w/2, y, f"M: {seller.get('Mobile','')} | E: {seller.get('Email','')}")
    
    c.line(30, y-10, w-30, y-10)
    
    # Bill To
    y_bill = y-40
    c.setFont("Helvetica-Bold", 10); c.drawString(40, y_bill, "Bill To:")
    c.setFont("Helvetica", 10)
    c.drawString(40, y_bill-15, buyer.get('Name',''))
    c.drawString(40, y_bill-30, f"GSTIN: {buyer.get('GSTIN','')}")
    c.drawString(40, y_bill-45, f"Addr: {buyer.get('Address 1','')}")

    # Invoice Details
    c.setFont("Helvetica-Bold", 10); c.drawString(400, y_bill, "Invoice Details:")
    c.setFont("Helvetica", 10)
    c.drawString(400, y_bill-15, f"No: {inv_no}")
    c.drawString(400, y_bill-30, f"Date: {buyer.get('Date','')}")
    
    # Table
    data = [["Item", "HSN", "Qty", "Rate", "Amount"]]
    for i in items:
        data.append([i['Description'], i.get('HSN',''), str(i['Qty']), str(i['Rate']), f"{i['Qty']*i['Rate']:.2f}"])
    
    data.append(["Taxable", "", "", "", f"{totals['taxable']:.2f}"])
    data.append(["Tax", "", "", "", f"{totals['total'] - totals['taxable']:.2f}"])
    data.append(["Total", "", "", "", f"{totals['total']:.2f}"])
    
    table = Table(data, colWidths=[2.5*inch, 0.8*inch, 0.6*inch, 0.8*inch, 1.2*inch])
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (-1,0), (-1,-1), 'RIGHT')
    ]))
    
    w_t, h_t = table.wrapOn(c, w, h)
    table.drawOn(c, 30, y_bill - 80 - h_t)
    
    # Footer
    c.setFont("Helvetica", 8)
    c.drawCentredString(w/2, 30, "Generated via HisaabKeeper Cloud")
    c.save()
    buffer.seek(0)
    return buffer

# --- HELPER: WHATSAPP & EMAIL ---
def get_whatsapp_link(mobile, msg):
    if not mobile: return None
    return f"https://wa.me/91{mobile}?text={urllib.parse.quote(msg)}"

# --- AUTHENTICATION ---
if "user_id" not in st.session_state: st.session_state.user_id = None
if "user_profile" not in st.session_state: st.session_state.user_profile = {}

def login_page():
    st.markdown("<h1 style='text-align:center;'>🔐 HisaabKeeper Login</h1>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Login", "Register New ID"])
    
    with tab1:
        with st.form("login_form"):
            uid = st.text_input("User ID (Unique)")
            pwd = st.text_input("Password", type="password")
            if st.form_submit_button("Login", type="primary"):
                df_users = fetch_data("Users")
                # Check user
                user_row = df_users[(df_users["UserID"] == uid) & (df_users["Password"] == pwd)]
                
                if not user_row.empty:
                    st.session_state.user_id = uid
                    # Load profile into session
                    st.session_state.user_profile = user_row.iloc[0].to_dict()
                    st.success(f"Welcome back, {st.session_state.user_profile.get('Business Name')}!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Invalid User ID or Password")

    with tab2:
        st.write("Create a new Company Profile (Data saved to Cloud Database)")
        with st.form("reg_form"):
            new_uid = st.text_input("Choose User ID (e.g. HK001)")
            new_pwd = st.text_input("Choose Password", type="password")
            bn = st.text_input("Business Name")
            gstin = st.text_input("GSTIN")
            mob = st.text_input("Mobile No")
            
            if st.form_submit_button("Register & Save Profile"):
                df_users = fetch_data("Users")
                if new_uid in df_users["UserID"].values:
                    st.error("User ID already exists! Choose another.")
                elif not new_uid or not new_pwd:
                    st.error("ID and Password are required.")
                else:
                    new_user = {
                        "UserID": new_uid, "Password": new_pwd, 
                        "Business Name": bn, "GSTIN": gstin, "Mobile": mob,
                        "Is GST": "Yes" if gstin else "No"
                    }
                    save_row_to_sheet("Users", new_user)
                    st.success("Registration Successful! Please Login.")

# --- MAIN APP (AFTER LOGIN) ---
def main_app():
    profile = st.session_state.user_profile
    st.sidebar.title(f"🏢 {profile.get('Business Name')}")
    st.sidebar.caption(f"ID: {st.session_state.user_id}")
    
    menu = ["Dashboard", "Customer Master", "Billing", "Ledger", "Inward", "Profile"]
    choice = st.sidebar.radio("Menu", menu)
    
    if st.sidebar.button("Logout"):
        st.session_state.user_id = None
        st.session_state.user_profile = {}
        st.rerun()

    # --- DASHBOARD ---
    if choice == "Dashboard":
        st.header("📊 Dashboard")
        # Load User's Data Only
        df_inv = fetch_user_data("Invoices")
        df_inw = fetch_user_data("Inward")
        
        # Numeric cleanup
        for col in ["Invoice Value", "Taxable"]:
             if col in df_inv.columns: df_inv[col] = pd.to_numeric(df_inv[col], errors='coerce').fillna(0)
        
        if "Total Value" in df_inw.columns: df_inw["Total Value"] = pd.to_numeric(df_inw["Total Value"], errors='coerce').fillna(0)
        
        total_sales = df_inv["Invoice Value"].sum() if not df_inv.empty else 0
        total_purch = df_inw["Total Value"].sum() if not df_inw.empty else 0
        
        c1, c2 = st.columns(2)
        c1.metric("Total Sales", f"₹ {total_sales:,.0f}")
        c2.metric("Total Purchase", f"₹ {total_purch:,.0f}")
        
        st.subheader("Recent Invoices")
        st.dataframe(df_inv.tail(5), use_container_width=True)

    # --- CUSTOMER MASTER ---
    elif choice == "Customer Master":
        st.header("👥 Customers")
        with st.expander("Add New Customer"):
            with st.form("add_c"):
                name = st.text_input("Name")
                gst = st.text_input("GSTIN")
                mob = st.text_input("Mobile")
                addr = st.text_input("Address")
                if st.form_submit_button("Save"):
                    save_row_to_sheet("Customers", {
                        "Name": name, "GSTIN": gst, "Mobile": mob, "Address 1": addr
                    })
                    st.success("Customer Saved!")
                    st.rerun()
        
        df_cust = fetch_user_data("Customers")
        st.dataframe(df_cust, use_container_width=True)

    # --- BILLING ---
    elif choice == "Billing":
        st.header("🧾 New Invoice")
        df_cust = fetch_user_data("Customers")
        cust_list = ["Select"] + df_cust["Name"].tolist() if not df_cust.empty else ["Select"]
        
        c1, c2 = st.columns([2,1])
        sel_cust = c1.selectbox("Select Customer", cust_list)
        inv_date = c2.date_input("Date")
        inv_no = st.text_input("Invoice No (e.g. 001)")
        
        # Items
        if "items" not in st.session_state: st.session_state.items = pd.DataFrame([{"Description": "", "Qty": 1.0, "Rate": 0.0, "HSN": ""}])
        
        edited_items = st.data_editor(st.session_state.items, num_rows="dynamic", use_container_width=True)
        
        # Calc
        valid = edited_items[edited_items["Description"]!=""].copy()
        valid["Amount"] = valid["Qty"] * valid["Rate"]
        subtotal = valid["Amount"].sum()
        
        # Tax
        is_gst = profile.get("Is GST", "No") == "Yes"
        tax = subtotal * 0.18 if is_gst else 0
        total = subtotal + tax
        
        st.markdown(f"**Total: ₹ {total:,.2f}**")
        
        if st.button("Generate & Save", type="primary"):
            if sel_cust == "Select": st.error("Select Customer")
            else:
                # Save to GSheet
                save_row_to_sheet("Invoices", {
                    "Bill No": inv_no, "Date": str(inv_date), "Buyer Name": sel_cust,
                    "Invoice Value": total, "Taxable": subtotal, "Items": json.dumps(valid.to_dict('records'))
                })
                
                # Generate PDF
                cust_data = df_cust[df_cust["Name"] == sel_cust].iloc[0].to_dict()
                pdf_bytes = generate_pdf_buffer(profile, cust_data, valid.to_dict('records'), inv_no, {'taxable': subtotal, 'total': total})
                
                st.success("Invoice Saved to Database!")
                st.download_button("⬇️ Download PDF", pdf_bytes, f"Inv_{inv_no}.pdf", "application/pdf")
                
                # WhatsApp Link
                msg = f"Hello {sel_cust}, Invoice {inv_no} for Rs {total} is generated."
                wa_link = get_whatsapp_link(cust_data.get('Mobile'), msg)
                if wa_link: st.link_button("Send on WhatsApp", wa_link)

    # --- LEDGER ---
    elif choice == "Ledger":
        st.header("📒 Customer Ledger")
        df_cust = fetch_user_data("Customers")
        sel_cust = st.selectbox("Customer", ["Select"] + df_cust["Name"].tolist())
        
        if sel_cust != "Select":
            # Fetch User's Invoices and Receipts
            df_inv = fetch_user_data("Invoices")
            df_rec = fetch_user_data("Receipts")
            
            # Numeric conversion
            if "Invoice Value" in df_inv.columns: df_inv["Invoice Value"] = pd.to_numeric(df_inv["Invoice Value"], errors='coerce').fillna(0)
            if "Amount" in df_rec.columns: df_rec["Amount"] = pd.to_numeric(df_rec["Amount"], errors='coerce').fillna(0)

            # Filter for this customer
            cust_inv = df_inv[df_inv["Buyer Name"] == sel_cust]
            cust_rec = df_rec[df_rec["Party Name"] == sel_cust]
            
            total_billed = cust_inv["Invoice Value"].sum()
            total_paid = cust_rec["Amount"].sum()
            bal = total_billed - total_paid
            
            st.metric("Pending Balance", f"₹ {bal:,.2f}")
            
            with st.expander("Add Receipt"):
                amt = st.number_input("Amount Received")
                if st.button("Save Receipt"):
                    save_row_to_sheet("Receipts", {
                        "Date": str(date.today()), "Party Name": sel_cust, "Amount": amt, "Note": "Payment"
                    })
                    st.success("Saved!")
                    st.rerun()

    # --- INWARD ---
    elif choice == "Inward":
        st.header("🚚 Inward Supply")
        with st.form("inw"):
            sup = st.text_input("Supplier")
            val = st.number_input("Value")
            if st.form_submit_button("Save"):
                save_row_to_sheet("Inward", {"Date": str(date.today()), "Supplier Name": sup, "Total Value": val})
                st.success("Saved")

    # --- PROFILE ---
    elif choice == "Profile":
        st.header("⚙️ Profile")
        st.json(profile)
        st.info("To edit profile, please contact Admin (shreeganesh111976@gmail.com) directly to update the Users Sheet.")

# --- RUN APP ---
if st.session_state.user_id:
    main_app()
else:
    login_page()
