import streamlit as st
import pandas as pd
import json
import re

# ==========================================
# 1. Page Config & Authentication Logic
# ==========================================
st.set_page_config(page_title="Malekah API Hub", page_icon="🔐", layout="wide")

# دالة التحقق من الباسورد
def check_password():
    """Returns `True` if the user had a correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["username"] in st.secrets["users"] and \
           st.session_state["password"] == st.secrets["users"][st.session_state["username"]]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show inputs
        st.header("🔒 Login Required")
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error
        st.header("🔒 Login Required")
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("😕 User not found or password incorrect")
        return False
    else:
        # Password correct
        return True

# إذا لم يتم تسجيل الدخول، توقف هنا
if check_password():

    # ==========================================
    # START OF THE MAIN APP (LOGGED IN)
    # ==========================================

    # Initialize Session State Variables
    keys_to_init = [
        'gen_collection', 'gen_syntax_errors', 'gen_zero_warnings', 
        'insp_collection', 'insp_syntax_errors', 'insp_zero_warnings', 'insp_filename'
    ]
    for key in keys_to_init:
        if key not in st.session_state:
            st.session_state[key] = [] if 'errors' in key or 'warnings' in key else None

    st.title("🛠️ Malekah API Hub (Authorized Access)")
    st.markdown("---")
    
    # --- Sidebar Navigation ---
    with st.sidebar:
        st.header("📲 Select Mode")
        app_mode = st.radio("Choose Function:", ["🚀 Generator (Excel -> Postman)", "🔍 Inspector (Fix Existing JSON)"])
        st.markdown("---")
        if st.button("Logout"):
            del st.session_state["password_correct"]
            st.rerun()

    # ==========================================
    # 2. Shared Logic Functions
    # ==========================================
    def get_api_name_from_url(url):
        if not isinstance(url, str): return "Unknown"
        return url.strip().split('/')[-1]

    def extract_body_from_description(description):
        if not description: return "{}"
        match = re.search(r'Request Body Example--\s*(\{[\s\S]*?\})(\s*--Response--|$)', description)
        if match:
            raw_body = match.group(1).strip()
            try:
                raw_body = re.sub(r',\s*\}', '}', raw_body)
                raw_body = re.sub(r',\s*\]', ']', raw_body)
                raw_body = re.sub(r'\bTrue\b', 'true', raw_body)
                raw_body = re.sub(r'\bFalse\b', 'false', raw_body)
                return raw_body
            except:
                return raw_body
        return "{}"

    def find_zero_values(data, path=""):
        findings = []
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{path}.{key}" if path else key
                findings.extend(find_zero_values(value, new_path))
        elif isinstance(data, list):
            for index, value in enumerate(data):
                new_path = f"{path}[{index}]"
                findings.extend(find_zero_values(value, new_path))
        elif isinstance(data, str):
            if re.match(r'^[0-]+$', data) and '0' in data:
                findings.append(f"{path} = {data}")
        return findings

    def analyze_collection_structure(items, parent_path=""):
        syntax_errs = []
        zero_warns = []
        for i, item in enumerate(items):
            current_name = item.get('name', 'Unnamed')
            full_path = f"{parent_path} / {current_name}" if parent_path else current_name
            
            # Recurse if folder
            if 'item' in item:
                s_err, z_warn = analyze_collection_structure(item['item'], full_path)
                syntax_errs.extend(s_err)
                zero_warns.extend(z_warn)
            
            # Check Request Body
            if 'request' in item and 'body' in item['request']:
                body_data = item['request']['body']
                raw_body = body_data.get('raw', '').strip()
                if raw_body and raw_body != "{}":
                    try:
                        parsed = json.loads(raw_body)
                        zeros = find_zero_values(parsed)
                        if zeros:
                            zero_warns.append({"path": full_path, "item_ref": item, "body": raw_body, "issues": zeros})
                    except json.JSONDecodeError:
                        syntax_errs.append({"path": full_path, "item_ref": item, "body": raw_body})
        return syntax_errs, zero_warns

    # --- Test Scripts ---
    test_script_old_base = [
        "// 1. Check Status Code is 200", "pm.test(\"Old API: Status code is 200\", function () { pm.response.to.have.status(200); });",
        "// 2. Check Response is not empty", "pm.test(\"Old API: Response is not empty\", function () { pm.expect(pm.response.text()).to.not.be.empty; });",
        "// 3. Save Response", "try { var jsonData = pm.response.json(); pm.collectionVariables.set('previous_response', JSON.stringify(jsonData)); pm.collectionVariables.set('previous_status', pm.response.code); } catch (e) { pm.collectionVariables.set('previous_response', '{}'); pm.collectionVariables.set('previous_status', pm.response.code); }"
    ]
    test_script_new_smart = [
        "var _ = require('lodash');", "var oldResStr = pm.collectionVariables.get('previous_response');", "var oldStatus = pm.collectionVariables.get('previous_status');",
        "var oldRes = oldResStr ? JSON.parse(oldResStr) : {};", "var newRes = pm.response.json();", "var newStatus = pm.response.code;",
        "pm.test(\"New API: Status code is 200\", function () { pm.response.to.have.status(200); });", "pm.test(\"New API: Response is not empty\", function () { pm.expect(pm.response.text()).to.not.be.empty; });",
        "if (oldStatus != newStatus) { pm.test(\"Status Codes Match\", function () { pm.expect.fail(`CRITICAL: Status Mismatch! Old: ${oldStatus}, New: ${newStatus}`); }); }",
        "else { pm.test(\"Status Codes Match\", function () { pm.expect(newStatus).to.eql(oldStatus); }); pm.test(\"Deep Response Comparison\", function () { if (_.isEqual(oldRes, newRes)) { pm.expect(true).to.be.true; return; } var diffs = []; function findDiff(obj1, obj2, path) { var keys1 = _.keys(obj1); var keys2 = _.keys(obj2); var allKeys = _.union(keys1, keys2); allKeys.forEach(function (key) { var newPath = path ? path + '.' + key : key; if (!_.has(obj1, key)) diffs.push(`[SCHEMA] Added: '${newPath}'`); else if (!_.has(obj2, key)) diffs.push(`[SCHEMA] Missing: '${newPath}'`); else if (_.isObject(obj1[key]) && _.isObject(obj2[key])) findDiff(obj1[key], obj2[key], newPath); else if (!_.isEqual(obj1[key], obj2[key])) diffs.push(`[VALUE] Mismatch '${newPath}': Old='${obj1[key]}' vs New='${obj2[key]}'`); }); } findDiff(oldRes, newRes, ''); if (diffs.length > 0) { var msg = 'MISMATCH DETECTED:\\n' + diffs.join('\\n'); if(msg.length > 2000) msg = msg.substring(0, 2000) + '...'; pm.expect.fail(msg); } }); }"
    ]
    test_script_cancelled = ["", "pm.test(\"New API Version Cancelled\", function () { console.log(\"Old API Only. New version cancelled.\"); pm.expect(true).to.be.true; });"]

    # ==========================================
    # MODE 1: GENERATOR
    # ==========================================
    if app_mode == "🚀 Generator (Excel -> Postman)":
        st.subheader("🚀 Generator Mode")
        with st.sidebar:
            st.header("1. Upload Files")
            uploaded_csv = st.file_uploader("API URLs (CSV/Excel)", type=['csv', 'xlsx'])
            uploaded_swagger = st.file_uploader("Swagger JSON", type=['json'])
            st.header("2. Output Settings")
            coll_name = st.text_input("Collection Name", "Malekah Master Collection")
            file_name = st.text_input("Filename", "Malekah_Collection.json")
            generate_btn = st.button("Generate & Analyze", type="primary")

        if generate_btn and uploaded_csv and uploaded_swagger:
            with st.spinner("Generating..."):
                try:
                    df = pd.read_csv(uploaded_csv) if uploaded_csv.name.endswith('.csv') else pd.read_excel(uploaded_csv)
                    swagger = json.load(uploaded_swagger)
                    collection = {"info": {"name": coll_name, "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"}, "item": [], "variable": [{"key": "previous_response", "value": "", "type": "string"}, {"key": "previous_status", "value": "", "type": "string"}]}
                    col_old, col_new = df.columns[0], df.columns[1]
                    
                    for index, row in df.iterrows():
                        old_url = str(row[col_old]).strip()
                        new_url_raw = str(row[col_new]).strip()
                        if old_url == 'nan' or old_url == '': continue
                        old_name = get_api_name_from_url(old_url)
                        folder_name = f"{index + 1:02d}_{old_name}"
                        body_content, desc, clean_new_url, has_new = "{}", "", "", False
                        
                        url_match = re.search(r'(https?://[^\s]+)', new_url_raw)
                        if url_match and "---" not in new_url_raw:
                            has_new = True
                            clean_new_url = url_match.group(1)
                            path_match = re.search(r'/api/.*', clean_new_url)
                            if path_match:
                                rel_path = path_match.group(0)
                                for s_path, details in swagger.get('paths', {}).items():
                                    if s_path.lower() == rel_path.lower():
                                        op = details.get(list(details.keys())[0], {})
                                        desc = op.get('description', '')
                                        body_content = extract_body_from_description(desc)
                                        break
                        
                        folder = {"name": folder_name, "item": []}
                        old_req = {"name": f"Old_{old_name}", "event": [{"listen": "test", "script": {"exec": list(test_script_old_base), "type": "text/javascript"}}], "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "url": {"raw": old_url, "host": old_url.split('/')[2:3], "path": old_url.split('/')[3:]}, "body": {"mode": "raw", "raw": body_content, "options": {"raw": {"language": "json"}}}}}
                        
                        if has_new:
                            folder['item'].append(old_req)
                            new_name = get_api_name_from_url(clean_new_url)
                            new_req = {"name": f"New Core_{new_name}", "event": [{"listen": "test", "script": {"exec": test_script_new_smart, "type": "text/javascript"}}], "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "url": {"raw": clean_new_url, "host": clean_new_url.split('/')[2:3], "path": clean_new_url.split('/')[3:]}, "body": {"mode": "raw", "raw": body_content, "options": {"raw": {"language": "json"}}}, "description": desc}}
                            folder['item'].append(new_req)
                        else:
                            old_req['event'][0]['script']['exec'] += test_script_cancelled
                            folder['item'].append(old_req)
                        collection['item'].append(folder)
                    
                    s_err, z_warn = analyze_collection_structure(collection['item'])
                    st.session_state['gen_collection'] = collection
                    st.session_state['gen_syntax_errors'] = s_err
                    st.session_state['gen_zero_warnings'] = z_warn
                    st.success("Generation Complete!")
                except Exception as e: st.error(f"Error: {e}")

        # Generator Editor UI
        if st.session_state['gen_collection']:
            col_data, s_errors, z_warns = st.session_state['gen_collection'], st.session_state['gen_syntax_errors'], st.session_state['gen_zero_warnings']
            m1, m2, m3 = st.columns(3)
            m1.metric("Folders", len(col_data['item']))
            m2.metric("Syntax Errors", len(s_errors), delta_color="inverse")
            m3.metric("Zero Warnings", len(z_warns))
            
            tab1, tab2 = st.tabs(["🔴 Fix Syntax", "🟡 Fix Zeros"])
            with tab1:
                if not s_errors: st.success("No Syntax Errors")
                else:
                    for i, err in enumerate(s_errors):
                        st.markdown(f"**{err['path']}**")
                        key = f"gen_syn_{i}"
                        if key not in st.session_state: st.session_state[key] = err['body']
                        txt = st.text_area("Body", key=key, height=120)
                        try: json.loads(txt); st.caption("✅ Valid")
                        except: st.caption("❌ Invalid")
                        st.markdown("---")
                    if st.button("💾 Apply Syntax Fixes (Gen)"):
                        for i, err in enumerate(s_errors):
                            err['item_ref']['request']['body']['raw'] = st.session_state.get(f"gen_syn_{i}", err['body'])
                        st.session_state['gen_syntax_errors'] = []
                        st.rerun()
            with tab2:
                if not z_warns: st.success("No Zero Warnings")
                else:
                    for i, warn in enumerate(z_warns):
                        st.markdown(f"**{warn['path']}**")
                        for issue in warn['issues']: st.caption(f"⚠️ {issue}")
                        key = f"gen_zero_{i}"
                        if key not in st.session_state: st.session_state[key] = warn['body']
                        txt = st.text_area("Body", key=key, height=120)
                        st.markdown("---")
                    if st.button("💾 Apply Zero Fixes (Gen)"):
                        for i, warn in enumerate(z_warns):
                            warn['item_ref']['request']['body']['raw'] = st.session_state.get(f"gen_zero_{i}", warn['body'])
                        st.session_state['gen_zero_warnings'] = []
                        st.rerun()
            if not st.session_state['gen_syntax_errors']:
                st.download_button("📥 Download Generated Collection", json.dumps(col_data, indent=4, ensure_ascii=False), file_name, "application/json", type="primary")

    # ==========================================
    # MODE 2: INSPECTOR
    # ==========================================
    elif app_mode == "🔍 Inspector (Fix Existing JSON)":
        st.subheader("🔍 Inspector Mode")
        st.info("Upload ANY Postman Collection file.")
        with st.sidebar:
            uploaded_insp_file = st.file_uploader("Upload Collection JSON", type=['json'])
            if uploaded_insp_file:
                if st.button("🔍 Analyze File", type="primary"):
                    try:
                        loaded_json = json.load(uploaded_insp_file)
                        st.session_state['insp_collection'] = loaded_json
                        st.session_state['insp_filename'] = f"Fixed_{uploaded_insp_file.name}"
                        s_err, z_warn = analyze_collection_structure(loaded_json.get('item', []))
                        st.session_state['insp_syntax_errors'] = s_err
                        st.session_state['insp_zero_warnings'] = z_warn
                    except Exception as e: st.error(f"Invalid JSON: {e}")

        if st.session_state['insp_collection']:
            col_data, s_errors, z_warns = st.session_state['insp_collection'], st.session_state['insp_syntax_errors'], st.session_state['insp_zero_warnings']
            st.markdown(f"### File: `{st.session_state.get('insp_filename', 'collection.json')}`")
            m1, m2 = st.columns(2)
            m1.metric("Syntax Errors", len(s_errors), delta_color="inverse")
            m2.metric("Zero Warnings", len(z_warns))
            
            tab_i1, tab_i2 = st.tabs(["🔴 Fix Syntax", "🟡 Fix Zeros"])
            with tab_i1:
                if not s_errors: st.success("✅ Clean")
                else:
                    st.warning(f"Found {len(s_errors)} errors.")
                    for i, err in enumerate(s_errors):
                        st.markdown(f"**📂 {err['path']}**")
                        key = f"insp_syn_{i}"
                        if key not in st.session_state: st.session_state[key] = err['body']
                        current_text = st.text_area("Body", key=key, height=150)
                        try: json.loads(current_text); st.caption("✅ Valid")
                        except: st.caption("❌ Invalid")
                        st.markdown("---")
                    if st.button("💾 Apply Fixes (Inspector)"):
                        new_errors = []
                        for i, err in enumerate(s_errors):
                            txt = st.session_state.get(f"insp_syn_{i}", err['body'])
                            err['item_ref']['request']['body']['raw'] = txt
                            try: json.loads(txt)
                            except: new_errors.append(err)
                        st.session_state['insp_syntax_errors'] = new_errors
                        st.success("Fixes Applied!")
                        st.rerun()
            with tab_i2:
                if not z_warns: st.success("✅ Clean")
                else:
                    st.warning(f"Found {len(z_warns)} warnings.")
                    for i, warn in enumerate(z_warns):
                        st.markdown(f"**📂 {warn['path']}**")
                        for issue in warn['issues']: st.caption(f"⚠️ {issue}")
                        key = f"insp_zero_{i}"
                        if key not in st.session_state: st.session_state[key] = warn['body']
                        txt = st.text_area("Body", key=key, height=150)
                        st.markdown("---")
                    if st.button("💾 Apply Zero Fixes (Inspector)"):
                        for i, warn in enumerate(z_warns):
                            warn['item_ref']['request']['body']['raw'] = st.session_state.get(f"insp_zero_{i}", warn['body'])
                        st.session_state['insp_zero_warnings'] = []
                        st.success("Updated!")
                        st.rerun()
            st.markdown("---")
            if not st.session_state['insp_syntax_errors']:
                out_name = st.session_state.get('insp_filename', 'Fixed_Collection.json')
                st.download_button(f"📥 Download {out_name}", json.dumps(col_data, indent=4, ensure_ascii=False), out_name, "application/json", type="primary")
            else: st.error("⚠️ Fix RED errors to download.")