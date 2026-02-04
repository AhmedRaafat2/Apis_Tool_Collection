import streamlit as st
import pandas as pd
import json
import re
import io

#streamlit run app.py
# ==========================================
# 0. Configuration & Constants
# ==========================================
st.set_page_config(page_title="Malekah API Hub", page_icon="🔐", layout="wide")

# القائمة البيضاء للقيم الصفرية (منطق الملفات المرفقة)
ALLOWED_ZERO_KEYS = [
    'pregnancyWeek', 'pregnancyStage', 'ageStageId', 'date', 
    'rate', 'price', 'duration', 'time', 'day'
]

# --- سكربتات التيست (من ملف generate_smart_collection_v2.py) ---
TEST_SCRIPT_OLD_BASE = [
    "// 1. Check Status Code is 200",
    "pm.test(\"Old API: Status code is 200\", function () {",
    "    pm.response.to.have.status(200);",
    "});",
    "",
    "// 2. Check Business Success (New Added)",
    "try {",
    "    var jsonData = pm.response.json();",
    "    if (jsonData.hasOwnProperty('success')) {",
    "        pm.test(\"Old API: Business Logic Success\", function () {",
    "            pm.expect(jsonData.success).to.be.true;",
    "        });",
    "    }",
    "    // 3. Save Response & Time for Comparison",
    "    pm.collectionVariables.set('previous_response', JSON.stringify(jsonData));",
    "    pm.collectionVariables.set('previous_status', pm.response.code);",
    "    pm.collectionVariables.set('previous_time', pm.response.responseTime);", 
    "} catch (e) {",
    "    pm.collectionVariables.set('previous_response', '{}');",
    "    pm.collectionVariables.set('previous_status', pm.response.code);",
    "    pm.collectionVariables.set('previous_time', 0);",
    "}"
]

TEST_SCRIPT_NEW_SMART = [
    "var _ = require('lodash');",
    "",
    "// 1. Check Status Code is 200",
    "pm.test(\"New API: Status code is 200\", function () {",
    "    pm.response.to.have.status(200);",
    "});",
    "",
    "// 2. Business Logic Success Check (CRITICAL)",
    "var newRes = pm.response.json();",
    "if (newRes.hasOwnProperty('success')) {",
    "    pm.test(\"New API: Business Success (success=true)\", function () {",
    "        if(newRes.success === false) {",
    "             pm.expect.fail(`Business Fail: ${newRes.message || 'No Error Message'}`);",
    "        }",
    "        pm.expect(newRes.success).to.be.true;",
    "    });",
    "}",
    "",
    "// --- COMPARISON LOGIC ---",
    "var oldResStr = pm.collectionVariables.get('previous_response');",
    "var oldStatus = pm.collectionVariables.get('previous_status');",
    "var oldTime = pm.collectionVariables.get('previous_time');",
    "var oldRes = oldResStr ? JSON.parse(oldResStr) : {};",
    "var newStatus = pm.response.code;",
    "",
    "// 3. Compare Status Codes",
    "if (oldStatus != newStatus) {",
    "    pm.test(\"Status Comparison\", function () {",
    "        pm.expect.fail(`CRITICAL: Status Mismatch! Old: ${oldStatus}, New: ${newStatus}`);",
    "    });",
    "} else {",
    "    pm.test(\"Status Codes Match\", function () { pm.expect(newStatus).to.eql(oldStatus); });",
    "    ",
    "    // 4. Performance Check (Warning only)",
    "    if (oldTime > 0) {",
    "        pm.test(\"Performance Check (New vs Old)\", function () {",
    "            var threshold = Math.max(oldTime * 1.5, oldTime + 200);",
    "            pm.expect(pm.response.responseTime).to.be.below(threshold, `New API is too slow! Old: ${oldTime}ms, New: ${pm.response.responseTime}ms`);",
    "        });",
    "    }",
    "    ",
    "    // 5. Deep Content Comparison",
    "    pm.test(\"Deep Data Match\", function () {",
    "        if (_.isEqual(oldRes, newRes)) {",
    "            pm.expect(true).to.be.true;",
    "            return;",
    "        }",
    "        var diffs = [];",
    "        function findDiff(obj1, obj2, path) {",
    "            var keys1 = _.keys(obj1);",
    "            var keys2 = _.keys(obj2);",
    "            var allKeys = _.union(keys1, keys2);",
    "            allKeys.forEach(function (key) {",
    "                var newPath = path ? path + '.' + key : key;",
    "                if (!_.has(obj1, key)) diffs.push(`[NEW FIELD] '${newPath}'`);",
    "                else if (!_.has(obj2, key)) diffs.push(`[MISSING FIELD] '${newPath}'`);",
    "                else if (_.isObject(obj1[key]) && _.isObject(obj2[key])) findDiff(obj1[key], obj2[key], newPath);",
    "                else if (!_.isEqual(obj1[key], obj2[key])) diffs.push(`[VALUE DIFF] '${newPath}': Old(${obj1[key]}) vs New(${obj2[key]})`);",
    "            });",
    "        }",
    "        findDiff(oldRes, newRes, '');",
    "        if (diffs.length > 0) {",
    "             pm.expect.fail('MISMATCHES:\\n' + diffs.join('\\n'));",
    "        }",
    "    });",
    "}"
]

TEST_SCRIPT_CANCELLED = [
    "pm.test(\"API Cancelled\", function () {",
    "    console.warn(\"Old API Only. New version cancelled.\");",
    "    pm.expect(true).to.be.true;",
    "});"
]

# ==========================================
# 1. Logic Helpers (The Core Logic)
# ==========================================

def get_api_name_from_url(url):
    if not isinstance(url, str): return "Unknown"
    return url.strip().split('/')[-1]

def normalize_url(url):
    """تنظيف الرابط ومطابقته مع السواجر (منطق catch_emptyBody_but_has_example_v2.py)"""
    if isinstance(url, dict): url = url.get('raw', '')
    url = str(url)
    url = url.split('?')[0]
    # محاولة اصطياد المسار من بعد /api/
    api_match = re.search(r'(/api/.*)', url, re.IGNORECASE)
    if api_match: return api_match.group(1)
    # تنظيف عام
    cleaned = re.sub(r'^.*?://[^/]+', '', url)
    cleaned = re.sub(r'^.*\}\}', '', cleaned)
    if not cleaned.startswith('/'): cleaned = '/' + cleaned
    return cleaned

def extract_body_from_description(description):
    """استخراج البودي من الوصف (منطق generate_smart_collection_v2.py)"""
    if not description: return "{}"
    match = re.search(r'Request Body Example--\s*(\{[\s\S]*?\})(\s*--Response--|$)', description, re.IGNORECASE)
    if match:
        raw_body = match.group(1).strip()
        try:
            raw_body = re.sub(r',\s*\}', '}', raw_body)
            raw_body = re.sub(r',\s*\]', ']', raw_body)
            raw_body = re.sub(r'\bTrue\b', 'true', raw_body)
            raw_body = re.sub(r'\bFalse\b', 'false', raw_body)
            raw_body = re.sub(r'\/\/.*', '', raw_body)
            return raw_body
        except:
            return raw_body
    return "{}"

def find_zero_values(data, path=""):
    """البحث عن القيم الصفرية و GUIDs (منطق check_json_and_zeros_v3.py)"""
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
        # صيد GUIDs الصفرية
        if re.match(r'^[0-]+$', data) and '0' in data and len(data) > 5:
            findings.append(f"{path} = \"{data}\" (Empty GUID 🚨)")
    elif isinstance(data, (int, float)):
        # تجاهل البوليان
        if isinstance(data, bool): return []
        if data == 0:
            current_key = path.split('.')[-1]
            if current_key not in ALLOWED_ZERO_KEYS:
                findings.append(f"{path} = {data} (Zero Value ⚠️)")
    return findings

# --- دوال السواجر التكرارية (Advanced Recursion from context) ---
def resolve_ref(schema, swagger_data):
    if '$ref' in schema:
        ref_path = schema['$ref'].split('/')[-1]
        return swagger_data.get('components', {}).get('schemas', {}).get(ref_path, {})
    return schema

def generate_dummy_data(schema, swagger_data, depth=0):
    if depth > 3: return "..."
    if '$ref' in schema:
        resolved = resolve_ref(schema, swagger_data)
        return generate_dummy_data(resolved, swagger_data, depth)
    if 'allOf' in schema:
        combined_obj = {}
        for sub_schema in schema['allOf']:
            result = generate_dummy_data(sub_schema, swagger_data, depth)
            if isinstance(result, dict):
                combined_obj.update(result)
        return combined_obj
    if 'properties' in schema:
        obj_data = {}
        for prop_name, prop_schema in schema['properties'].items():
            obj_data[prop_name] = generate_dummy_data(prop_schema, swagger_data, depth + 1)
        return obj_data
    s_type = schema.get('type')
    if s_type == 'integer': return 0
    if s_type == 'number': return 0.0
    if s_type == 'boolean': return True
    if s_type == 'string':
        if 'format' in schema and schema['format'] == 'uuid': return "00000000-0000-0000-0000-000000000000"
        if 'format' in schema and 'date' in schema['format']: return "2024-01-01T00:00:00Z"
        return "string"
    if s_type == 'array':
        item_schema = schema.get('items', {})
        sample_item = generate_dummy_data(item_schema, swagger_data, depth + 1)
        return [sample_item]
    return "string"

def generate_body_hint_from_swagger(op_details, swagger_data):
    request_body = op_details.get('requestBody', {})
    content = request_body.get('content', {})
    target_schema = {}
    for mime in content:
        if 'json' in mime:
            target_schema = content[mime].get('schema', {})
            break
    if not target_schema:
        for p in op_details.get('parameters', []):
            if p.get('in') == 'body':
                target_schema = p.get('schema', {})
                break
    if not target_schema: return None
    final_body = generate_dummy_data(target_schema, swagger_data)
    return json.dumps(final_body, ensure_ascii=False, indent=2)

def find_swagger_path(normalized_url, swagger_paths):
    if normalized_url in swagger_paths: return swagger_paths[normalized_url]
    for s_path, s_data in swagger_paths.items():
        pattern = "^" + re.sub(r'\{.*?\}', '[^/]+', s_path) + "$"
        if re.match(pattern, normalized_url, re.IGNORECASE):
            return s_data
    return None

# --- دالة التحليل الرئيسية (Inspector Logic) ---
def analyze_collection_recursively(items, swagger_data=None, parent_path=""):
    syntax_errs = []
    zero_warns = []
    missing_bodies = []

    for i, item in enumerate(items):
        current_name = item.get('name', 'Unnamed')
        full_path = f"{parent_path} > {current_name}" if parent_path else current_name
        
        # Recursion
        if 'item' in item:
            s, z, m = analyze_collection_recursively(item['item'], swagger_data, full_path)
            syntax_errs.extend(s)
            zero_warns.extend(z)
            missing_bodies.extend(m)
        
        # Request Check
        elif 'request' in item:
            req_info = item['request']
            body_data = req_info.get('body', {})
            raw_body = body_data.get('raw', '').strip()
            url_raw = req_info.get('url', '')
            if isinstance(url_raw, dict): url_raw = url_raw.get('raw', '')
            
            # 1. Syntax & Zero Check (If body exists)
            if raw_body and raw_body != "{}":
                try:
                    parsed = json.loads(raw_body)
                    zeros = find_zero_values(parsed)
                    for z in zeros:
                        zero_warns.append({
                            "path": full_path, 
                            "item_ref": item, 
                            "body": raw_body, 
                            "detail": z
                        })
                except json.JSONDecodeError as e:
                    hint = f"Error at line {e.lineno}"
                    if "'" in raw_body and '"' not in raw_body: hint = "⚠️ Single Quotes used"
                    elif re.search(r',\s*\}', raw_body): hint = "⚠️ Trailing Comma"
                    elif re.search(r'\bTrue\b', raw_body): hint = "⚠️ Capitalized Boolean"
                    
                    syntax_errs.append({
                        "path": full_path, 
                        "item_ref": item, 
                        "body": raw_body, 
                        "hint": hint
                    })
            
            # 2. Missing Body Check (If Swagger is present)
            # Only checking if body is empty AND Swagger requires it
            if (not raw_body or raw_body == "{}") and swagger_data:
                # ignore 'Old' APIs in missing check if needed, but logic is generic here
                clean_path = normalize_url(url_raw)
                paths = swagger_data.get('paths', {})
                method = req_info.get('method', 'POST').lower()
                
                path_item = find_swagger_path(clean_path, paths)
                if path_item:
                    op = path_item.get(method)
                    if op:
                        hint_json = generate_body_hint_from_swagger(op, swagger_data)
                        if hint_json: # If hint generated, means body is expected
                            missing_bodies.append({
                                "path": full_path,
                                "item_ref": item,
                                "url": clean_path,
                                "hint": hint_json
                            })

    return syntax_errs, zero_warns, missing_bodies


# ==========================================
# 2. Authentication
# ==========================================
def check_password():
    """Returns `True` if the user had a correct password."""
    def password_entered():
        if st.session_state["username"] in st.secrets["users"] and \
           st.session_state["password"] == st.secrets["users"][st.session_state["username"]]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.header("🔒 Login Required")
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.header("🔒 Login Required")
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("😕 User not found or password incorrect")
        return False
    else:
        return True

if check_password():
    # ==========================================
    # 3. Main App UI
    # ==========================================
    
    # Init Session State
    keys_to_init = [
        'gen_collection', 'gen_syntax_errors', 'gen_zero_warnings', 
        'insp_collection', 'insp_syntax_errors', 'insp_zero_warnings', 'insp_missing_bodies', 'insp_filename', 'insp_swagger'
    ]
    for key in keys_to_init:
        if key not in st.session_state:
            st.session_state[key] = [] if 'errors' in key or 'warnings' in key or 'bodies' in key else None

    st.title("🛠️ Malekah API Hub (Authorized)")
    st.markdown("---")

    with st.sidebar:
        st.header("📲 Select Mode")
        app_mode = st.radio("Choose Function:", ["🚀 Generator (Excel -> Postman)", "🔍 Inspector (Fix Existing JSON)"])
        st.markdown("---")
        if st.button("Logout"):
            del st.session_state["password_correct"]
            st.rerun()

    # ------------------------------------------
    # MODE 1: GENERATOR (generate_smart_collection_v2 logic)
    # ------------------------------------------
    if app_mode == "🚀 Generator (Excel -> Postman)":
        st.subheader("🚀 Generator Mode")
        st.caption("Generate a Postman Collection comparing Old vs New APIs using Swagger descriptions.")
        
        with st.sidebar:
            st.header("1. Upload Files")
            uploaded_csv = st.file_uploader("API URLs (CSV/Excel)", type=['csv', 'xlsx'])
            uploaded_swagger_gen = st.file_uploader("Swagger JSON", type=['json'], key="sw_gen")
            
            st.header("2. Output Settings")
            coll_name = st.text_input("Collection Name", "Malekah Master Collection")
            file_name = st.text_input("Filename", "Malekah_Collection.json")
            generate_btn = st.button("Generate & Analyze", type="primary")

        if generate_btn and uploaded_csv and uploaded_swagger_gen:
            with st.spinner("Processing..."):
                try:
                    df = pd.read_csv(uploaded_csv) if uploaded_csv.name.endswith('.csv') else pd.read_excel(uploaded_csv)
                    swagger = json.load(uploaded_swagger_gen)
                    
                    collection = {
                        "info": {"name": coll_name, "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"}, 
                        "item": [], 
                        "variable": [{"key": "previous_response", "value": "", "type": "string"}, 
                                     {"key": "previous_status", "value": "", "type": "string"},
                                     {"key": "previous_time", "value": "0", "type": "string"}]
                    }
                    
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
                            
                            # Swagger Extraction
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
                        
                        old_req = {
                            "name": f"Old_{old_name}", 
                            "event": [{"listen": "test", "script": {"exec": list(TEST_SCRIPT_OLD_BASE), "type": "text/javascript"}}], 
                            "request": {
                                "method": "POST", 
                                "header": [{"key": "Content-Type", "value": "application/json"}], 
                                "url": {"raw": old_url, "host": old_url.split('/')[2:3], "path": old_url.split('/')[3:]}, 
                                "body": {"mode": "raw", "raw": body_content, "options": {"raw": {"language": "json"}}}
                            }
                        }
                        
                        if has_new:
                            folder['item'].append(old_req)
                            new_name = get_api_name_from_url(clean_new_url)
                            new_req = {
                                "name": f"New Core_{new_name}", 
                                "event": [{"listen": "test", "script": {"exec": TEST_SCRIPT_NEW_SMART, "type": "text/javascript"}}], 
                                "request": {
                                    "method": "POST", 
                                    "header": [{"key": "Content-Type", "value": "application/json"}], 
                                    "url": {"raw": clean_new_url, "host": clean_new_url.split('/')[2:3], "path": clean_new_url.split('/')[3:]}, 
                                    "body": {"mode": "raw", "raw": body_content, "options": {"raw": {"language": "json"}}}, 
                                    "description": desc
                                }
                            }
                            folder['item'].append(new_req)
                        else:
                            old_req['event'][0]['script']['exec'] += TEST_SCRIPT_CANCELLED
                            folder['item'].append(old_req)
                            
                        collection['item'].append(folder)
                    
                    # Store Result
                    st.session_state['gen_collection'] = collection
                    
                    # Auto Analyze Generated Collection (Syntax/Zeros)
                    s_err, z_warn, _ = analyze_collection_recursively(collection['item'], None)
                    st.session_state['gen_syntax_errors'] = s_err
                    st.session_state['gen_zero_warnings'] = z_warn
                    st.success("Generation Complete!")
                    
                except Exception as e:
                    st.error(f"Error during generation: {e}")

        # Generator Result UI
        if st.session_state['gen_collection']:
            col_data = st.session_state['gen_collection']
            s_errors = st.session_state['gen_syntax_errors']
            z_warns = st.session_state['gen_zero_warnings']
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Generated Folders", len(col_data['item']))
            m2.metric("Syntax Issues", len(s_errors), delta_color="inverse")
            m3.metric("Zero/GUID Warnings", len(z_warns), delta_color="inverse")
            
            tab1, tab2 = st.tabs(["🔴 Fix Syntax (Generated)", "🟡 Fix Zeros (Generated)"])
            
            with tab1:
                if not s_errors: st.success("✅ JSON Syntax is perfect.")
                else:
                    for i, err in enumerate(s_errors):
                        st.markdown(f"**📂 {err['path']}**")
                        st.caption(f"Error Hint: {err.get('hint', 'Unknown')}")
                        key = f"gen_syn_{i}"
                        if key not in st.session_state: st.session_state[key] = err['body']
                        txt = st.text_area("Body", key=key, height=120)
                        try: json.loads(txt); st.caption("✅ Valid")
                        except: st.caption("❌ Invalid")
                        st.divider()
                    
                    if st.button("💾 Apply Syntax Fixes"):
                        for i, err in enumerate(s_errors):
                            err['item_ref']['request']['body']['raw'] = st.session_state.get(f"gen_syn_{i}", err['body'])
                        st.session_state['gen_syntax_errors'] = []
                        st.rerun()

            with tab2:
                if not z_warns: st.success("✅ No Zero Value/Empty GUID warnings.")
                else:
                    for i, warn in enumerate(z_warns):
                        st.markdown(f"**📂 {warn['path']}**")
                        st.caption(f"⚠️ Issue: {warn['detail']}")
                        key = f"gen_zero_{i}"
                        if key not in st.session_state: st.session_state[key] = warn['body']
                        txt = st.text_area("Body", key=key, height=120)
                        st.divider()
                    
                    if st.button("💾 Apply Zero Fixes"):
                        for i, warn in enumerate(z_warns):
                            warn['item_ref']['request']['body']['raw'] = st.session_state.get(f"gen_zero_{i}", warn['body'])
                        st.session_state['gen_zero_warnings'] = []
                        st.rerun()

            st.download_button("📥 Download Generated Collection", json.dumps(col_data, indent=4, ensure_ascii=False), file_name, "application/json", type="primary")

    # ------------------------------------------
    # MODE 2: INSPECTOR (check_json_and_zeros + catch_emptyBody logic)
    # ------------------------------------------
    elif app_mode == "🔍 Inspector (Fix Existing JSON)":
        st.subheader("🔍 Inspector Mode")
        st.info("Upload an existing Postman Collection to fix Syntax, Zeros, and find Missing Bodies.")
        
        with st.sidebar:
            uploaded_insp_file = st.file_uploader("Upload Collection JSON", type=['json'])
            uploaded_swagger_insp = st.file_uploader("Upload Swagger (Optional for Body Hints)", type=['json'], key="sw_insp")
            
            if uploaded_insp_file:
                if st.button("🔍 Analyze File", type="primary"):
                    try:
                        loaded_json = json.load(uploaded_insp_file)
                        swagger_data = json.load(uploaded_swagger_insp) if uploaded_swagger_insp else None
                        
                        st.session_state['insp_collection'] = loaded_json
                        st.session_state['insp_filename'] = f"Fixed_{uploaded_insp_file.name}"
                        st.session_state['insp_swagger'] = swagger_data
                        
                        s_err, z_warn, m_bodies = analyze_collection_recursively(loaded_json.get('item', []), swagger_data)
                        
                        st.session_state['insp_syntax_errors'] = s_err
                        st.session_state['insp_zero_warnings'] = z_warn
                        st.session_state['insp_missing_bodies'] = m_bodies
                    except Exception as e: st.error(f"Invalid JSON: {e}")

        if st.session_state['insp_collection']:
            col_data = st.session_state['insp_collection']
            s_errors = st.session_state['insp_syntax_errors']
            z_warns = st.session_state['insp_zero_warnings']
            m_bodies = st.session_state['insp_missing_bodies']
            
            st.markdown(f"### File: `{st.session_state.get('insp_filename', 'collection.json')}`")
            m1, m2, m3 = st.columns(3)
            m1.metric("Syntax Errors", len(s_errors), delta_color="inverse")
            m2.metric("Zero/GUID Warnings", len(z_warns), delta_color="inverse")
            m3.metric("Missing Bodies", len(m_bodies), delta_color="inverse")

            tab_i1, tab_i2, tab_i3 = st.tabs(["🔴 Fix Syntax", "🟡 Fix Zeros", "🔵 Missing Bodies"])
            
            with tab_i1:
                if not s_errors: st.success("✅ Clean")
                else:
                    st.warning(f"Found {len(s_errors)} Syntax errors.")
                    for i, err in enumerate(s_errors):
                        st.markdown(f"**📂 {err['path']}**")
                        st.caption(f"Hint: {err.get('hint', '')}")
                        key = f"insp_syn_{i}"
                        if key not in st.session_state: st.session_state[key] = err['body']
                        txt = st.text_area("Body", key=key, height=150)
                        try: json.loads(txt); st.caption("✅ Valid")
                        except: st.caption("❌ Invalid")
                        st.divider()
                    
                    if st.button("💾 Apply Syntax Fixes"):
                        new_errors = []
                        for i, err in enumerate(s_errors):
                            txt = st.session_state.get(f"insp_syn_{i}", err['body'])
                            err['item_ref']['request']['body']['raw'] = txt
                            try: json.loads(txt)
                            except: new_errors.append(err)
                        st.session_state['insp_syntax_errors'] = new_errors
                        st.rerun()

            with tab_i2:
                if not z_warns: st.success("✅ Clean")
                else:
                    st.warning(f"Found {len(z_warns)} Zero Value/Empty GUID warnings.")
                    for i, warn in enumerate(z_warns):
                        st.markdown(f"**📂 {warn['path']}**")
                        st.caption(f"⚠️ Issue: {warn['detail']}")
                        key = f"insp_zero_{i}"
                        if key not in st.session_state: st.session_state[key] = warn['body']
                        txt = st.text_area("Body", key=key, height=150)
                        st.divider()
                    
                    if st.button("💾 Apply Zero Fixes"):
                        for i, warn in enumerate(z_warns):
                            warn['item_ref']['request']['body']['raw'] = st.session_state.get(f"insp_zero_{i}", warn['body'])
                        st.session_state['insp_zero_warnings'] = []
                        st.rerun()
            
            with tab_i3:
                if not m_bodies: 
                    st.success("✅ All requests have bodies (or Swagger not provided).")
                else:
                    st.info(f"Found {len(m_bodies)} requests empty in Postman but required in Swagger.")
                    for i, miss in enumerate(m_bodies):
                        st.markdown(f"**📂 {miss['path']}**")
                        st.code(miss['url'], language="http")
                        key = f"insp_miss_{i}"
                        st.caption("Suggested Body (from Swagger Schema):")
                        # Here we use text_area to allow user to verify before applying
                        if key not in st.session_state: st.session_state[key] = miss['hint']
                        txt = st.text_area("Body to Insert", key=key, height=200)
                        st.divider()
                    
                    if st.button("💾 Fill Missing Bodies"):
                        for i, miss in enumerate(m_bodies):
                            txt = st.session_state.get(f"insp_miss_{i}", miss['hint'])
                            miss['item_ref']['request']['body']['raw'] = txt
                        st.session_state['insp_missing_bodies'] = []
                        st.success("Bodies Filled Successfully!")
                        st.rerun()

            st.divider()
            if not st.session_state['insp_syntax_errors']:
                out_name = st.session_state.get('insp_filename', 'Fixed_Collection.json')
                st.download_button(f"📥 Download {out_name}", json.dumps(col_data, indent=4, ensure_ascii=False), out_name, "application/json", type="primary")
            else:
                st.error("⚠️ Please fix all Red Syntax Errors before downloading.")