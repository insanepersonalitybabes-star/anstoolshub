from flask import Flask, render_template, request, jsonify, send_file, Response, session, redirect, url_for
from PIL import Image
import io, base64, urllib.parse, math, random, string, qrcode, requests, json, os, colorsys, sqlite3, hashlib, difflib, re
from fpdf import FPDF
from datetime import datetime, date, timedelta
from collections import Counter
from functools import wraps

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = os.environ.get('SESSION_SECRET', 'anstools-secret-key-2026')

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'anstools.db')

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS tool_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_slug TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            uses INTEGER DEFAULT 0,
            date TEXT NOT NULL,
            UNIQUE(tool_slug, date)
        );
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, email TEXT, subject TEXT, message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS tool_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_slug TEXT, suggestion_type TEXT,
            suggestion TEXT, email TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    ''')
    defaults = [
        ('adsense_publisher_id', 'ca-pub-XXXXXXXXXXXXXXXX'),
        ('adsense_slot_1', '1111111111'),
        ('adsense_slot_2', '2222222222'),
        ('ga_measurement_id', 'G-XXXXXXXXXX'),
        ('site_title', 'ANS Tools'),
        ('contact_email', 'hello@anstools.xyz'),
        ('admin_password_hash', hashlib.sha256('anstools2026'.encode()).hexdigest()),
        ('robots_txt', 'User-agent: *\nAllow: /\nSitemap: https://anstools.xyz/sitemap.xml'),
    ]
    for key, value in defaults:
        conn.execute('INSERT OR IGNORE INTO site_settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

init_db()

def get_setting(key, default=''):
    try:
        conn = get_db()
        row = conn.execute('SELECT value FROM site_settings WHERE key=?', (key,)).fetchone()
        conn.close()
        return row['value'] if row else default
    except:
        return default

def set_setting(key, value):
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO site_settings (key,value) VALUES (?,?)', (key, value))
    conn.commit()
    conn.close()

def track_view(slug):
    try:
        today = date.today().isoformat()
        conn = get_db()
        conn.execute('''INSERT INTO tool_stats (tool_slug,views,uses,date) VALUES (?,1,0,?)
            ON CONFLICT(tool_slug,date) DO UPDATE SET views=views+1''', (slug, today))
        conn.commit(); conn.close()
    except: pass

def track_use(slug):
    try:
        today = date.today().isoformat()
        conn = get_db()
        conn.execute('''INSERT INTO tool_stats (tool_slug,views,uses,date) VALUES (?,0,1,?)
            ON CONFLICT(tool_slug,date) DO UPDATE SET uses=uses+1''', (slug, today))
        conn.commit(); conn.close()
    except: pass

@app.context_processor
def inject_settings():
    return dict(
        g_adsense_pub=get_setting('adsense_publisher_id','ca-pub-XXXXXXXXXXXXXXXX'),
        g_adsense_slot1=get_setting('adsense_slot_1','1111111111'),
        g_adsense_slot2=get_setting('adsense_slot_2','2222222222'),
        g_ga_id=get_setting('ga_measurement_id','G-XXXXXXXXXX'),
        g_site_title=get_setting('site_title','ANS Tools'),
    )

# ── Admin Auth ────────────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ── Tools Registry ────────────────────────────────────────────────────────────
TOOLS = [
    {"name":"Image Compressor","slug":"image-compressor","category":"images","icon":"compress","desc":"Reduce image file size without quality loss","popular":True},
    {"name":"Image Resizer","slug":"image-resizer","category":"images","icon":"expand","desc":"Resize images to any pixel dimension instantly","popular":True},
    {"name":"Image to PDF","slug":"image-to-pdf","category":"images","icon":"file-image","desc":"Convert multiple images into a single PDF"},
    {"name":"JPG to PNG","slug":"jpg-to-png","category":"images","icon":"image","desc":"Convert JPG images to PNG with transparency support"},
    {"name":"PNG to JPG","slug":"png-to-jpg","category":"images","icon":"image","desc":"Convert PNG to JPG with adjustable quality"},
    {"name":"PDF Merger","slug":"pdf-merger","category":"pdf","icon":"file-pdf","desc":"Merge multiple PDF files into one document","popular":True},
    {"name":"Word Counter","slug":"word-counter","category":"text","icon":"align-left","desc":"Count words, characters, sentences and reading time","popular":True},
    {"name":"Case Converter","slug":"case-converter","category":"text","icon":"type","desc":"Convert text to UPPER, lower, Title and more cases"},
    {"name":"Base64 Encoder","slug":"base64","category":"text","icon":"code","desc":"Encode and decode Base64 strings instantly"},
    {"name":"URL Encoder","slug":"url-encoder","category":"text","icon":"link","desc":"Encode and decode URLs and special characters"},
    {"name":"Age Calculator","slug":"age-calculator","category":"calculators","icon":"calendar","desc":"Calculate exact age in years, months and days","popular":True},
    {"name":"BMI Calculator","slug":"bmi-calculator","category":"calculators","icon":"activity","desc":"Calculate Body Mass Index with health category"},
    {"name":"Percentage Calculator","slug":"percentage-calculator","category":"calculators","icon":"percent","desc":"Calculate percentages, changes and ratios"},
    {"name":"Unit Converter","slug":"unit-converter","category":"converters","icon":"refresh-cw","desc":"Convert length, weight, temperature, speed and more"},
    {"name":"Random Number","slug":"random-number","category":"calculators","icon":"shuffle","desc":"Generate random numbers in any range and quantity"},
    {"name":"Text to Speech","slug":"text-to-speech","category":"text","icon":"volume-2","desc":"Convert text to audio using browser voices"},
    {"name":"QR Code Generator","slug":"qr-generator","category":"text","icon":"grid","desc":"Create QR codes for URLs, text and contacts","popular":True},
    {"name":"EMI Calculator","slug":"emi-calculator","category":"calculators","icon":"credit-card","desc":"Calculate loan EMI and amortization schedule"},
    {"name":"Tip Calculator","slug":"tip-calculator","category":"calculators","icon":"dollar-sign","desc":"Split bills and calculate tips per person"},
    {"name":"Invoice Generator","slug":"invoice-generator","category":"pdf","icon":"file-text","desc":"Create professional PDF invoices in seconds"},
    {"name":"Password Generator","slug":"password-generator","category":"text","icon":"lock","desc":"Generate strong, secure passwords instantly","popular":True},
    {"name":"Color Picker","slug":"color-picker","category":"converters","icon":"droplet","desc":"Pick colors and convert HEX, RGB, HSL values"},
    {"name":"Meta Tag Generator","slug":"meta-tag-generator","category":"text","icon":"tag","desc":"Generate SEO meta tags for any webpage"},
    {"name":"TikTok Downloader","slug":"tiktok-downloader","category":"downloaders","icon":"video","desc":"Download TikTok videos without watermark","popular":True},
    {"name":"Instagram Downloader","slug":"instagram-downloader","category":"downloaders","icon":"instagram","desc":"Download Instagram photos and Reels"},
    {"name":"YouTube Thumbnail","slug":"youtube-thumbnail","category":"downloaders","icon":"youtube","desc":"Download HD thumbnails from any YouTube video","new":True},
    {"name":"JSON Formatter","slug":"json-formatter","category":"text","icon":"braces","desc":"Format, validate and beautify JSON data","new":True},
    {"name":"Readability Checker","slug":"readability-checker","category":"text","icon":"book-open","desc":"Analyze text readability with Flesch-Kincaid score","new":True},
    {"name":"Text Diff Checker","slug":"text-diff","category":"text","icon":"git-diff","desc":"Compare two texts and highlight differences","new":True},
]

CATEGORIES = [
    {"id":"all","label":"All Tools","icon":"grid"},
    {"id":"images","label":"Image Tools","icon":"image"},
    {"id":"pdf","label":"PDF Tools","icon":"file-text"},
    {"id":"text","label":"Text Tools","icon":"type"},
    {"id":"calculators","label":"Calculators","icon":"calculator"},
    {"id":"converters","label":"Converters","icon":"refresh-cw"},
    {"id":"downloaders","label":"Downloaders","icon":"download"},
]

# ── Sitemap & Robots ──────────────────────────────────────────────────────────
@app.route('/sitemap.xml')
def sitemap():
    urls = ['https://anstools.xyz/', 'https://anstools.xyz/about', 'https://anstools.xyz/contact']
    for t in TOOLS:
        urls.append(f"https://anstools.xyz/tools/{t['slug']}")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += f'  <url><loc>{u}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>\n'
    xml += '</urlset>'
    return Response(xml, mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    content = get_setting('robots_txt', 'User-agent: *\nAllow: /\nSitemap: https://anstools.xyz/sitemap.xml')
    return Response(content, mimetype='text/plain')

# ── Contact & Suggestions ─────────────────────────────────────────────────────
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    success = False
    error = None
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        email = request.form.get('email','').strip()
        subject = request.form.get('subject','').strip()
        message = request.form.get('message','').strip()
        if name and email and message:
            try:
                conn = get_db()
                conn.execute('INSERT INTO contact_messages (name,email,subject,message) VALUES (?,?,?,?)',
                             (name, email, subject, message))
                conn.commit(); conn.close()
                success = True
            except:
                error = 'Failed to send message. Please try again.'
        else:
            error = 'Please fill in all required fields.'
    return render_template('contact.html',
        title="Contact Us - ANS Tools",
        description="Get in touch with the ANS Tools team.",
        keywords="contact ans tools",
        canonical="https://anstools.xyz/contact",
        success=success, error=error)

@app.route('/api/suggest', methods=['POST'])
def suggest():
    try:
        data = request.get_json() or {}
        tool_slug = data.get('tool_slug','general')
        suggestion_type = data.get('type','suggestion')
        suggestion = data.get('suggestion','').strip()
        email = data.get('email','').strip()
        if not suggestion:
            return jsonify({'ok': False, 'error': 'Empty suggestion'})
        conn = get_db()
        conn.execute('INSERT INTO tool_suggestions (tool_slug,suggestion_type,suggestion,email) VALUES (?,?,?,?)',
                     (tool_slug, suggestion_type, suggestion, email))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── Public Pages ──────────────────────────────────────────────────────────────
@app.route('/')
def index():
    popular = [t for t in TOOLS if t.get('popular')]
    new_tools = [t for t in TOOLS if t.get('new')]
    return render_template('index.html',
        title="ANS Tools - Free Online Tools for Everyone",
        description="29+ free online tools for images, PDF, text, calculators, converters and more. No signup. Works on any device.",
        keywords="free online tools, image compressor, pdf merger, word counter, calculator, converter",
        canonical="https://anstools.xyz",
        tools=TOOLS, categories=CATEGORIES, popular=popular, new_tools=new_tools)

@app.route('/about')
def about():
    return render_template('about.html',
        title="About - ANS Tools | Free Online Tools Platform",
        description="ANS Tools provides 29+ free online tools. Learn about our mission to make powerful utilities accessible to everyone.",
        keywords="about ans tools",
        canonical="https://anstools.xyz/about",
        tools=TOOLS)

@app.route('/privacy-policy')
def privacy():
    return render_template('privacy.html',
        title="Privacy Policy - ANS Tools",
        description="Read the ANS Tools privacy policy.",
        keywords="privacy policy ans tools",
        canonical="https://anstools.xyz/privacy-policy")

@app.route('/terms')
def terms():
    return render_template('terms.html',
        title="Terms of Service - ANS Tools",
        description="Read the ANS Tools terms of service.",
        keywords="terms ans tools",
        canonical="https://anstools.xyz/terms")

@app.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html',
        title="Disclaimer - ANS Tools",
        description="Read the ANS Tools disclaimer.",
        keywords="disclaimer ans tools",
        canonical="https://anstools.xyz/disclaimer")

# ── Admin Panel ───────────────────────────────────────────────────────────────
@app.route('/xpanel-7749')
def admin_index():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_login'))

@app.route('/xpanel-7749/login', methods=['GET','POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        pw = request.form.get('password','')
        stored_hash = get_setting('admin_password_hash')
        if hashlib.sha256(pw.encode()).hexdigest() == stored_hash:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        error = 'Incorrect password.'
    return render_template('admin/login.html', error=error)

@app.route('/xpanel-7749/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/xpanel-7749/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db()
    today = date.today().isoformat()
    thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()
    total_views = conn.execute('SELECT SUM(views) as v FROM tool_stats').fetchone()['v'] or 0
    total_uses = conn.execute('SELECT SUM(uses) as u FROM tool_stats').fetchone()['u'] or 0
    today_views = conn.execute('SELECT SUM(views) as v FROM tool_stats WHERE date=?',(today,)).fetchone()['v'] or 0
    top_tools = conn.execute('''SELECT tool_slug, SUM(views) as tv, SUM(uses) as tu
        FROM tool_stats GROUP BY tool_slug ORDER BY tv DESC LIMIT 10''').fetchall()
    recent_msgs = conn.execute('SELECT * FROM contact_messages ORDER BY created_at DESC LIMIT 5').fetchall()
    recent_sugg = conn.execute('SELECT * FROM tool_suggestions ORDER BY created_at DESC LIMIT 5').fetchall()
    unread_msgs = conn.execute('SELECT COUNT(*) as c FROM contact_messages WHERE is_read=0').fetchone()['c']
    # Last 14 days traffic
    daily = conn.execute('''SELECT date, SUM(views) as v FROM tool_stats
        WHERE date >= ? GROUP BY date ORDER BY date''', (thirty_days_ago,)).fetchall()
    conn.close()
    return render_template('admin/dashboard.html',
        total_views=total_views, total_uses=total_uses, today_views=today_views,
        top_tools=top_tools, recent_msgs=recent_msgs, recent_sugg=recent_sugg,
        unread_msgs=unread_msgs, daily=daily, tools=TOOLS)

@app.route('/xpanel-7749/settings', methods=['GET','POST'])
@admin_required
def admin_settings():
    success = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'adsense':
            set_setting('adsense_publisher_id', request.form.get('publisher_id',''))
            set_setting('adsense_slot_1', request.form.get('slot_1',''))
            set_setting('adsense_slot_2', request.form.get('slot_2',''))
            success = 'AdSense settings saved.'
        elif action == 'analytics':
            set_setting('ga_measurement_id', request.form.get('ga_id',''))
            success = 'Google Analytics settings saved.'
        elif action == 'general':
            set_setting('site_title', request.form.get('site_title',''))
            set_setting('contact_email', request.form.get('contact_email',''))
            success = 'General settings saved.'
        elif action == 'password':
            current_pw = request.form.get('current_password','')
            new_pw = request.form.get('new_password','')
            stored_hash = get_setting('admin_password_hash')
            if hashlib.sha256(current_pw.encode()).hexdigest() == stored_hash:
                if len(new_pw) >= 8:
                    set_setting('admin_password_hash', hashlib.sha256(new_pw.encode()).hexdigest())
                    success = 'Password changed successfully.'
                else:
                    success = 'ERROR: Password must be at least 8 characters.'
            else:
                success = 'ERROR: Current password is incorrect.'
    settings = {
        'publisher_id': get_setting('adsense_publisher_id'),
        'slot_1': get_setting('adsense_slot_1'),
        'slot_2': get_setting('adsense_slot_2'),
        'ga_id': get_setting('ga_measurement_id'),
        'site_title': get_setting('site_title'),
        'contact_email': get_setting('contact_email'),
    }
    return render_template('admin/settings.html', settings=settings, success=success)

@app.route('/xpanel-7749/seo', methods=['GET','POST'])
@admin_required
def admin_seo():
    success = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'robots':
            set_setting('robots_txt', request.form.get('robots_txt',''))
            success = 'Robots.txt saved.'
    robots = get_setting('robots_txt')
    return render_template('admin/seo.html', robots=robots, success=success, tools=TOOLS)

@app.route('/xpanel-7749/messages', methods=['GET','POST'])
@admin_required
def admin_messages():
    if request.method == 'POST':
        action = request.form.get('action')
        msg_id = request.form.get('id')
        conn = get_db()
        if action == 'read':
            conn.execute('UPDATE contact_messages SET is_read=1 WHERE id=?', (msg_id,))
        elif action == 'delete':
            conn.execute('DELETE FROM contact_messages WHERE id=?', (msg_id,))
        conn.commit(); conn.close()
    conn = get_db()
    messages = conn.execute('SELECT * FROM contact_messages ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin/messages.html', messages=messages)

@app.route('/xpanel-7749/suggestions', methods=['GET','POST'])
@admin_required
def admin_suggestions():
    if request.method == 'POST':
        action = request.form.get('action')
        sid = request.form.get('id')
        conn = get_db()
        if action == 'approve':
            conn.execute("UPDATE tool_suggestions SET status='approved' WHERE id=?", (sid,))
        elif action == 'reject':
            conn.execute("UPDATE tool_suggestions SET status='rejected' WHERE id=?", (sid,))
        elif action == 'delete':
            conn.execute('DELETE FROM tool_suggestions WHERE id=?', (sid,))
        conn.commit(); conn.close()
    conn = get_db()
    suggestions = conn.execute('SELECT * FROM tool_suggestions ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin/suggestions.html', suggestions=suggestions)

# ── Image Tools ───────────────────────────────────────────────────────────────
@app.route('/tools/image-compressor', methods=['GET','POST'])
def image_compressor():
    track_view('image-compressor')
    result = None
    if request.method == 'POST':
        track_use('image-compressor')
        if 'image' not in request.files:
            result = {'error': 'No file uploaded'}
        else:
            f = request.files['image']
            quality = int(request.form.get('quality', 80))
            img = Image.open(f)
            img_io = io.BytesIO()
            fmt = img.format if img.format else 'JPEG'
            if fmt == 'PNG' and quality < 100:
                img.save(img_io, format='PNG', optimize=True)
            else:
                if img.mode in ('RGBA','P'): img = img.convert('RGB')
                img.save(img_io, format='JPEG', quality=quality, optimize=True)
                fmt = 'JPEG'
            img_io.seek(0)
            data = img_io.getvalue()
            b64 = base64.b64encode(data).decode()
            ext = 'jpg' if fmt == 'JPEG' else 'png'
            result = {'b64': b64, 'ext': ext, 'new_size': len(data), 'mime': f'image/{"jpeg" if fmt=="JPEG" else "png"}'}
    related = [t for t in TOOLS if t['category']=='images' and t['slug']!='image-compressor'][:4]
    return render_template('tools/image_compressor.html',
        title="Image Compressor - Free Online | ANS Tools",
        description="Compress images online for free. Reduce image file size without losing quality. Supports JPG, PNG. No signup required.",
        keywords="image compressor, compress image online, reduce image size",
        canonical="https://anstools.xyz/tools/image-compressor",
        result=result, related=related, slug='image-compressor')

@app.route('/tools/image-resizer', methods=['GET','POST'])
def image_resizer():
    track_view('image-resizer')
    result = None
    if request.method == 'POST':
        track_use('image-resizer')
        if 'image' not in request.files:
            result = {'error': 'No file uploaded'}
        else:
            f = request.files['image']
            width = int(request.form.get('width', 800))
            height = int(request.form.get('height', 600))
            maintain_ratio = request.form.get('maintain_ratio') == 'on'
            img = Image.open(f)
            if maintain_ratio:
                img.thumbnail((width, height), Image.LANCZOS)
            else:
                img = img.resize((width, height), Image.LANCZOS)
            img_io = io.BytesIO()
            if img.mode in ('RGBA','P'): img = img.convert('RGB')
            img.save(img_io, format='JPEG', quality=90)
            img_io.seek(0)
            data = img_io.getvalue()
            b64 = base64.b64encode(data).decode()
            result = {'b64': b64, 'width': img.width, 'height': img.height, 'new_size': len(data)}
    related = [t for t in TOOLS if t['category']=='images' and t['slug']!='image-resizer'][:4]
    return render_template('tools/image_resizer.html',
        title="Image Resizer - Free Online | ANS Tools",
        description="Resize images online for free. Change image dimensions in pixels. Maintain aspect ratio option.",
        keywords="image resizer, resize image online",
        canonical="https://anstools.xyz/tools/image-resizer",
        result=result, related=related, slug='image-resizer')

@app.route('/tools/image-to-pdf', methods=['GET','POST'])
def image_to_pdf():
    track_view('image-to-pdf')
    result = None
    if request.method == 'POST':
        track_use('image-to-pdf')
        files = request.files.getlist('images')
        if not files or not files[0].filename:
            result = {'error': 'No files uploaded'}
        else:
            pdf = FPDF()
            for f in files:
                img = Image.open(f)
                if img.mode in ('RGBA','P'): img = img.convert('RGB')
                img_io = io.BytesIO()
                img.save(img_io, format='JPEG', quality=90)
                img_io.seek(0)
                pdf.add_page()
                w, h = img.size
                ratio = min(210/w, 297/h)
                nw, nh = w*ratio*3.7795, h*ratio*3.7795
                x, y = (210-nw/3.7795)/2, (297-nh/3.7795)/2
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    tmp.write(img_io.getvalue()); tmp_path = tmp.name
                pdf.image(tmp_path, x=x, y=y, w=nw/3.7795, h=nh/3.7795)
                os.unlink(tmp_path)
            b64 = base64.b64encode(bytes(pdf.output())).decode()
            result = {'b64': b64, 'count': len(files)}
    related = [t for t in TOOLS if t['category'] in ('images','pdf') and t['slug']!='image-to-pdf'][:4]
    return render_template('tools/image_to_pdf.html',
        title="Image to PDF - Free Online | ANS Tools",
        description="Convert images to PDF online for free. Multiple images to one PDF. JPG, PNG supported.",
        keywords="image to pdf, convert image to pdf online",
        canonical="https://anstools.xyz/tools/image-to-pdf",
        result=result, related=related, slug='image-to-pdf')

@app.route('/tools/jpg-to-png', methods=['GET','POST'])
def jpg_to_png():
    track_view('jpg-to-png')
    result = None
    if request.method == 'POST':
        track_use('jpg-to-png')
        if 'image' not in request.files:
            result = {'error': 'No file uploaded'}
        else:
            f = request.files['image']
            img = Image.open(f)
            img_io = io.BytesIO()
            img.save(img_io, format='PNG')
            img_io.seek(0)
            data = img_io.getvalue()
            result = {'b64': base64.b64encode(data).decode(), 'new_size': len(data)}
    related = [t for t in TOOLS if t['category']=='images' and t['slug']!='jpg-to-png'][:4]
    return render_template('tools/jpg_to_png.html',
        title="JPG to PNG Converter - Free Online | ANS Tools",
        description="Convert JPG to PNG online for free. High quality JPEG to PNG conversion. No watermark.",
        keywords="jpg to png, convert jpg to png online",
        canonical="https://anstools.xyz/tools/jpg-to-png",
        result=result, related=related, slug='jpg-to-png')

@app.route('/tools/png-to-jpg', methods=['GET','POST'])
def png_to_jpg():
    track_view('png-to-jpg')
    result = None
    if request.method == 'POST':
        track_use('png-to-jpg')
        if 'image' not in request.files:
            result = {'error': 'No file uploaded'}
        else:
            f = request.files['image']
            quality = int(request.form.get('quality', 90))
            img = Image.open(f)
            if img.mode in ('RGBA','P','LA'):
                bg = Image.new('RGB', img.size, (255,255,255))
                if img.mode == 'P': img = img.convert('RGBA')
                bg.paste(img, mask=img.split()[3] if img.mode=='RGBA' else None)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            img_io = io.BytesIO()
            img.save(img_io, format='JPEG', quality=quality)
            img_io.seek(0)
            data = img_io.getvalue()
            result = {'b64': base64.b64encode(data).decode(), 'new_size': len(data)}
    related = [t for t in TOOLS if t['category']=='images' and t['slug']!='png-to-jpg'][:4]
    return render_template('tools/png_to_jpg.html',
        title="PNG to JPG Converter - Free Online | ANS Tools",
        description="Convert PNG to JPG online for free. Transparent PNG to white background JPG.",
        keywords="png to jpg, convert png to jpg online",
        canonical="https://anstools.xyz/tools/png-to-jpg",
        result=result, related=related, slug='png-to-jpg')

# ── PDF Tools ─────────────────────────────────────────────────────────────────
@app.route('/tools/pdf-merger', methods=['GET','POST'])
def pdf_merger():
    track_view('pdf-merger')
    result = None
    if request.method == 'POST':
        track_use('pdf-merger')
        files = request.files.getlist('pdfs')
        if not files or not files[0].filename:
            result = {'error': 'No files uploaded'}
        else:
            try:
                import PyPDF2
                writer = PyPDF2.PdfWriter()
                for f in files:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        writer.add_page(page)
                pdf_io = io.BytesIO()
                writer.write(pdf_io)
                pdf_io.seek(0)
                data = pdf_io.getvalue()
                result = {'b64': base64.b64encode(data).decode(), 'count': len(files)}
            except Exception as e:
                result = {'error': str(e)}
    related = [t for t in TOOLS if t['category']=='pdf' and t['slug']!='pdf-merger'][:4]
    return render_template('tools/pdf_merger.html',
        title="PDF Merger - Free Online | ANS Tools",
        description="Merge multiple PDF files into one online for free. Easy PDF combiner. No watermark.",
        keywords="pdf merger, merge pdf online, combine pdf files",
        canonical="https://anstools.xyz/tools/pdf-merger",
        result=result, related=related, slug='pdf-merger')

# ── Text Tools ────────────────────────────────────────────────────────────────
@app.route('/tools/word-counter', methods=['GET','POST'])
def word_counter():
    track_view('word-counter')
    result = None
    if request.method == 'POST':
        track_use('word-counter')
        text = request.form.get('text','')
        if text.strip():
            words = text.split()
            clean_words = [w.strip('.,!?;:\'"()[]{}').lower() for w in words if len(w.strip('.,!?;:\'"()[]{}')) > 2]
            result = {
                'words': len(words),
                'characters': len(text),
                'characters_no_spaces': len(text.replace(' ','')),
                'sentences': text.count('.')+text.count('!')+text.count('?'),
                'paragraphs': len([p for p in text.split('\n\n') if p.strip()]),
                'reading_time': round(len(words)/238, 1),
                'speaking_time': round(len(words)/150, 1),
                'top_keywords': Counter(clean_words).most_common(5),
                'text': text
            }
        else:
            result = {'error': 'Please enter some text'}
    related = [t for t in TOOLS if t['category']=='text' and t['slug']!='word-counter'][:4]
    return render_template('tools/word_counter.html',
        title="Word Counter - Free Online | ANS Tools",
        description="Count words, characters, sentences and paragraphs online for free. Get reading time and top keywords.",
        keywords="word counter, character counter, count words online",
        canonical="https://anstools.xyz/tools/word-counter",
        result=result, related=related, slug='word-counter')

@app.route('/tools/case-converter', methods=['GET','POST'])
def case_converter():
    track_view('case-converter')
    result = None
    if request.method == 'POST':
        track_use('case-converter')
        text = request.form.get('text','')
        conversion = request.form.get('conversion','upper')
        if text:
            cases = {
                'upper': text.upper(), 'lower': text.lower(),
                'title': text.title(),
                'sentence': '. '.join(s.strip().capitalize() for s in text.split('.')),
                'alternate': ''.join(c.upper() if i%2==0 else c.lower() for i,c in enumerate(text)),
                'inverse': text.swapcase()
            }
            result = {'converted': cases.get(conversion, text), 'text': text, 'conversion': conversion}
        else:
            result = {'error': 'Please enter some text'}
    related = [t for t in TOOLS if t['category']=='text' and t['slug']!='case-converter'][:4]
    return render_template('tools/case_converter.html',
        title="Case Converter - Free Online | ANS Tools",
        description="Convert text case online for free. UPPERCASE, lowercase, Title Case, Sentence case instantly.",
        keywords="case converter, text case converter, uppercase lowercase",
        canonical="https://anstools.xyz/tools/case-converter",
        result=result, related=related, slug='case-converter')

@app.route('/tools/base64', methods=['GET','POST'])
def base64_tool():
    track_view('base64')
    result = None
    if request.method == 'POST':
        track_use('base64')
        text = request.form.get('text','')
        action = request.form.get('action','encode')
        if text:
            try:
                if action == 'encode':
                    result = {'output': base64.b64encode(text.encode('utf-8')).decode('utf-8'), 'action': 'encoded'}
                else:
                    result = {'output': base64.b64decode(text).decode('utf-8'), 'action': 'decoded'}
            except Exception as e:
                result = {'error': f'Invalid input: {e}'}
        else:
            result = {'error': 'Please enter some text'}
    related = [t for t in TOOLS if t['category']=='text' and t['slug']!='base64'][:4]
    return render_template('tools/base64_tool.html',
        title="Base64 Encoder/Decoder - Free Online | ANS Tools",
        description="Encode and decode Base64 online for free. Instant Base64 encoding and decoding.",
        keywords="base64 encoder decoder, base64 encode online",
        canonical="https://anstools.xyz/tools/base64",
        result=result, related=related, slug='base64')

@app.route('/tools/url-encoder', methods=['GET','POST'])
def url_encoder():
    track_view('url-encoder')
    result = None
    if request.method == 'POST':
        track_use('url-encoder')
        text = request.form.get('text','')
        action = request.form.get('action','encode')
        if text:
            output = urllib.parse.quote(text) if action=='encode' else urllib.parse.unquote(text)
            result = {'output': output, 'action': action+'d'}
        else:
            result = {'error': 'Please enter some text'}
    related = [t for t in TOOLS if t['category']=='text' and t['slug']!='url-encoder'][:4]
    return render_template('tools/url_encoder.html',
        title="URL Encoder/Decoder - Free Online | ANS Tools",
        description="Encode and decode URLs online for free. Percent-encode special characters in URLs.",
        keywords="url encoder decoder, url encode online",
        canonical="https://anstools.xyz/tools/url-encoder",
        result=result, related=related, slug='url-encoder')

@app.route('/tools/text-to-speech')
def text_to_speech():
    track_view('text-to-speech')
    related = [t for t in TOOLS if t['category']=='text' and t['slug']!='text-to-speech'][:4]
    return render_template('tools/text_to_speech.html',
        title="Text to Speech - Free Online | ANS Tools",
        description="Convert text to speech online for free. Multiple voices and speeds. Browser-based.",
        keywords="text to speech, tts online",
        canonical="https://anstools.xyz/tools/text-to-speech",
        related=related, slug='text-to-speech')

@app.route('/tools/qr-generator', methods=['GET','POST'])
def qr_generator():
    track_view('qr-generator')
    result = None
    if request.method == 'POST':
        track_use('qr-generator')
        text = request.form.get('text','')
        size = int(request.form.get('size', 10))
        if text:
            qr = qrcode.QRCode(version=1, box_size=size, border=4)
            qr.add_data(text)
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')
            img_io = io.BytesIO()
            img.save(img_io, format='PNG')
            img_io.seek(0)
            result = {'b64': base64.b64encode(img_io.getvalue()).decode(), 'text': text}
        else:
            result = {'error': 'Please enter text or URL to generate QR code'}
    related = [t for t in TOOLS if t['slug'] in ('password-generator','meta-tag-generator','word-counter','color-picker')]
    return render_template('tools/qr_generator.html',
        title="QR Code Generator - Free Online | ANS Tools",
        description="Generate QR codes online for free. Create QR codes for URLs, text, contacts. Download as PNG.",
        keywords="qr code generator, create qr code online",
        canonical="https://anstools.xyz/tools/qr-generator",
        result=result, related=related, slug='qr-generator')

@app.route('/tools/meta-tag-generator', methods=['GET','POST'])
def meta_tag_generator():
    track_view('meta-tag-generator')
    result = None
    if request.method == 'POST':
        track_use('meta-tag-generator')
        title = request.form.get('title','')
        description = request.form.get('description','')
        keywords = request.form.get('keywords','')
        author = request.form.get('author','')
        canonical = request.form.get('canonical','')
        og_image = request.form.get('og_image','')
        twitter_handle = request.form.get('twitter_handle','')
        tags = [f'<!-- Primary Meta Tags -->\n<title>{title}</title>',
                f'<meta name="title" content="{title}">',
                f'<meta name="description" content="{description}">']
        if keywords: tags.append(f'<meta name="keywords" content="{keywords}">')
        if author: tags.append(f'<meta name="author" content="{author}">')
        if canonical: tags.append(f'<link rel="canonical" href="{canonical}">')
        tags += [f'\n<!-- Open Graph -->\n<meta property="og:type" content="website">',
                 f'<meta property="og:title" content="{title}">',
                 f'<meta property="og:description" content="{description}">']
        if canonical: tags.append(f'<meta property="og:url" content="{canonical}">')
        if og_image: tags.append(f'<meta property="og:image" content="{og_image}">')
        tags += [f'\n<!-- Twitter Card -->\n<meta name="twitter:card" content="summary_large_image">',
                 f'<meta name="twitter:title" content="{title}">',
                 f'<meta name="twitter:description" content="{description}">']
        if twitter_handle: tags.append(f'<meta name="twitter:site" content="@{twitter_handle.lstrip("@")}">')
        if og_image: tags.append(f'<meta name="twitter:image" content="{og_image}">')
        result = {'tags': '\n'.join(tags)}
    related = [t for t in TOOLS if t['slug'] in ('word-counter','qr-generator','password-generator','base64')]
    return render_template('tools/meta_tag_generator.html',
        title="Meta Tag Generator - Free Online | ANS Tools",
        description="Generate SEO meta tags for your website. Open Graph, Twitter Card, and standard meta tags.",
        keywords="meta tag generator, seo meta tags",
        canonical="https://anstools.xyz/tools/meta-tag-generator",
        result=result, related=related, slug='meta-tag-generator')

@app.route('/tools/password-generator', methods=['GET','POST'])
def password_generator():
    track_view('password-generator')
    result = None
    if request.method == 'POST':
        track_use('password-generator')
        length = min(int(request.form.get('length', 16)), 128)
        use_upper = request.form.get('uppercase') == 'on'
        use_lower = request.form.get('lowercase') == 'on'
        use_numbers = request.form.get('numbers') == 'on'
        use_symbols = request.form.get('symbols') == 'on'
        chars = ''
        if use_upper: chars += string.ascii_uppercase
        if use_lower: chars += string.ascii_lowercase
        if use_numbers: chars += string.digits
        if use_symbols: chars += '!@#$%^&*()_+-=[]{}|;:,.<>?'
        if not chars: chars = string.ascii_letters + string.digits
        password = ''.join(random.choice(chars) for _ in range(length))
        types = sum([use_upper, use_lower, use_numbers, use_symbols])
        if length >= 16 and types >= 3:
            strength, color, pct = 'Strong', '#10B981', 90
        elif length >= 10 and types >= 2:
            strength, color, pct = 'Medium', '#F59E0B', 55
        else:
            strength, color, pct = 'Weak', '#EF4444', 25
        result = {'password': password, 'strength': strength, 'strength_color': color, 'strength_pct': pct}
    related = [t for t in TOOLS if t['slug'] in ('qr-generator','base64','meta-tag-generator','word-counter')]
    return render_template('tools/password_generator.html',
        title="Password Generator - Free Online | ANS Tools",
        description="Generate strong, secure passwords online for free. Customize length and character types.",
        keywords="password generator, strong password generator",
        canonical="https://anstools.xyz/tools/password-generator",
        result=result, related=related, slug='password-generator')

@app.route('/tools/color-picker', methods=['GET','POST'])
def color_picker():
    track_view('color-picker')
    result = None
    if request.method == 'POST':
        track_use('color-picker')
        hex_color = request.form.get('hex','#2563EB').lstrip('#')
        try:
            r,g,b = int(hex_color[0:2],16), int(hex_color[2:4],16), int(hex_color[4:6],16)
            h,l,s = colorsys.rgb_to_hls(r/255, g/255, b/255)
            hh,ss,vv = colorsys.rgb_to_hsv(r/255, g/255, b/255)
            result = {
                'hex': f'#{hex_color.upper()}', 'rgb': f'rgb({r},{g},{b})',
                'hsl': f'hsl({round(h*360)},{round(s*100)}%,{round(l*100)}%)',
                'hsv': f'hsv({round(hh*360)},{round(ss*100)}%,{round(vv*100)}%)',
                'r': r, 'g': g, 'b': b, 'hex_val': hex_color.upper()
            }
        except:
            result = {'error': 'Invalid hex color'}
    related = [t for t in TOOLS if t['slug'] in ('qr-generator','image-compressor','meta-tag-generator','password-generator')]
    return render_template('tools/color_picker.html',
        title="Color Picker - Free Online | ANS Tools",
        description="Pick colors and convert between HEX, RGB, and HSL online for free.",
        keywords="color picker, hex to rgb, color converter",
        canonical="https://anstools.xyz/tools/color-picker",
        result=result, related=related, slug='color-picker')

# ── Calculator Tools ──────────────────────────────────────────────────────────
@app.route('/tools/age-calculator', methods=['GET','POST'])
def age_calculator():
    track_view('age-calculator')
    result = None
    if request.method == 'POST':
        track_use('age-calculator')
        dob_str = request.form.get('dob','')
        if dob_str:
            try:
                dob = date.fromisoformat(dob_str)
                today = date.today()
                if dob > today:
                    result = {'error': 'Date cannot be in the future'}
                else:
                    years = today.year - dob.year
                    months = today.month - dob.month
                    days = today.day - dob.day
                    if days < 0:
                        months -= 1
                        prev = today.replace(day=1) - __import__('datetime').timedelta(days=1)
                        days += prev.day
                    if months < 0:
                        years -= 1; months += 12
                    total_days = (today - dob).days
                    nby = today.year if (today.month,today.day)<=(dob.month,dob.day) else today.year+1
                    try: next_bday = date(nby, dob.month, dob.day)
                    except: next_bday = date(nby, dob.month, 28)
                    result = {
                        'years': years, 'months': months, 'days': days,
                        'total_days': total_days, 'total_months': years*12+months,
                        'total_weeks': total_days//7, 'total_hours': total_days*24,
                        'day_of_week': dob.strftime('%A'),
                        'dob_formatted': dob.strftime('%B %d, %Y'),
                        'days_to_bday': (next_bday-today).days,
                        'next_bday': next_bday.strftime('%B %d, %Y')
                    }
            except ValueError:
                result = {'error': 'Invalid date'}
        else:
            result = {'error': 'Please enter a date of birth'}
    related = [t for t in TOOLS if t['category']=='calculators' and t['slug']!='age-calculator'][:4]
    return render_template('tools/age_calculator.html',
        title="Age Calculator - Free Online | ANS Tools",
        description="Calculate exact age in years, months, and days online for free. Find days to next birthday.",
        keywords="age calculator, calculate age online, birthday calculator",
        canonical="https://anstools.xyz/tools/age-calculator",
        result=result, related=related, slug='age-calculator')

@app.route('/tools/bmi-calculator', methods=['GET','POST'])
def bmi_calculator():
    track_view('bmi-calculator')
    result = None
    if request.method == 'POST':
        track_use('bmi-calculator')
        unit = request.form.get('unit','metric')
        try:
            if unit == 'metric':
                weight = float(request.form.get('weight',0))
                height = float(request.form.get('height',0))/100
            else:
                weight = float(request.form.get('weight',0))*0.453592
                height = (float(request.form.get('height_ft',0))*12+float(request.form.get('height_in',0)))*0.0254
            if height<=0 or weight<=0:
                result = {'error': 'Please enter valid height and weight'}
            else:
                bmi = round(weight/(height**2),1)
                if bmi<18.5: cat,color,pct = 'Underweight','#F59E0B',max(5,bmi/18.5*25)
                elif bmi<25: cat,color,pct = 'Normal weight','#10B981',25+(bmi-18.5)/6.5*25
                elif bmi<30: cat,color,pct = 'Overweight','#F59E0B',50+(bmi-25)/5*25
                else: cat,color,pct = 'Obese','#EF4444',min(95,75+(bmi-30)/10*25)
                result = {'bmi': bmi, 'category': cat, 'color': color, 'percent': round(pct,1)}
        except: result = {'error': 'Please enter valid numbers'}
    related = [t for t in TOOLS if t['category']=='calculators' and t['slug']!='bmi-calculator'][:4]
    return render_template('tools/bmi_calculator.html',
        title="BMI Calculator - Free Online | ANS Tools",
        description="Calculate your Body Mass Index (BMI) online for free. Metric and imperial units.",
        keywords="bmi calculator, body mass index calculator",
        canonical="https://anstools.xyz/tools/bmi-calculator",
        result=result, related=related, slug='bmi-calculator')

@app.route('/tools/percentage-calculator', methods=['GET','POST'])
def percentage_calculator():
    track_view('percentage-calculator')
    result = None
    if request.method == 'POST':
        track_use('percentage-calculator')
        mode = request.form.get('mode','1')
        try:
            if mode=='1':
                x,y = float(request.form.get('x',0)), float(request.form.get('y',0))
                res = round((x/100)*y, 2)
                result = {'answer': res, 'mode': 1, 'label': f"{x}% of {y} = {res}"}
            elif mode=='2':
                x,y = float(request.form.get('x',0)), float(request.form.get('y',0))
                res = round((x/y)*100,2) if y else None
                result = {'answer': res, 'mode': 2, 'label': f"{x} is {res}% of {y}"} if res is not None else {'error': 'Cannot divide by zero'}
            elif mode=='3':
                x,y = float(request.form.get('x',0)), float(request.form.get('y',0))
                res = round(((y-x)/x)*100,2) if x else None
                label = 'increase' if res and res>=0 else 'decrease'
                result = {'answer': abs(res), 'mode': 3, 'label': f"{abs(res)}% {label} from {x} to {y}"} if res is not None else {'error': 'Cannot divide by zero'}
        except: result = {'error': 'Please enter valid numbers'}
    related = [t for t in TOOLS if t['category']=='calculators' and t['slug']!='percentage-calculator'][:4]
    return render_template('tools/percentage_calculator.html',
        title="Percentage Calculator - Free Online | ANS Tools",
        description="Calculate percentages online for free. Find percentage of a number, percentage change.",
        keywords="percentage calculator, calculate percentage",
        canonical="https://anstools.xyz/tools/percentage-calculator",
        result=result, related=related, slug='percentage-calculator')

@app.route('/tools/unit-converter', methods=['GET','POST'])
def unit_converter():
    track_view('unit-converter')
    result = None
    conversions = {
        'length': {'mm':0.001,'cm':0.01,'m':1,'km':1000,'inch':0.0254,'foot':0.3048,'yard':0.9144,'mile':1609.344},
        'weight': {'mg':0.000001,'g':0.001,'kg':1,'ton':1000,'oz':0.028349,'lb':0.453592},
        'volume': {'ml':0.001,'l':1,'gallon':3.78541,'quart':0.946353,'pint':0.473176,'cup':0.236588,'fl_oz':0.029574},
        'speed': {'kmh':1,'mph':1.60934,'ms':3.6,'knot':1.852},
    }
    if request.method == 'POST':
        track_use('unit-converter')
        category = request.form.get('category','length')
        from_unit = request.form.get('from_unit','m')
        to_unit = request.form.get('to_unit','km')
        try:
            value = float(request.form.get('value',0))
            if category == 'temperature':
                fu,tu = request.form.get('from_unit','celsius'), request.form.get('to_unit','fahrenheit')
                c = value if fu=='celsius' else (value-32)*5/9 if fu=='fahrenheit' else value-273.15
                converted = c if tu=='celsius' else c*9/5+32 if tu=='fahrenheit' else c+273.15
                result = {'value':value,'converted':round(converted,4),'from_unit':fu,'to_unit':tu,'category':category}
            elif category in conversions:
                units = conversions[category]
                if from_unit in units and to_unit in units:
                    converted = round(value*units[from_unit]/units[to_unit],6)
                    result = {'value':value,'converted':converted,'from_unit':from_unit,'to_unit':to_unit,'category':category}
                else: result = {'error':'Invalid units'}
        except: result = {'error':'Please enter a valid number'}
    related = [t for t in TOOLS if t['category']=='converters' and t['slug']!='unit-converter'][:4]
    return render_template('tools/unit_converter.html',
        title="Unit Converter - Free Online | ANS Tools",
        description="Convert units online for free. Length, weight, temperature, volume, speed conversions.",
        keywords="unit converter, length converter, weight converter",
        canonical="https://anstools.xyz/tools/unit-converter",
        result=result, related=related, slug='unit-converter', conversions=conversions)

@app.route('/tools/random-number', methods=['GET','POST'])
def random_number():
    track_view('random-number')
    result = None
    if request.method == 'POST':
        track_use('random-number')
        try:
            mn, mx = int(request.form.get('min',1)), int(request.form.get('max',100))
            count = min(int(request.form.get('count',1)),100)
            if mn>mx: result={'error':'Min must be less than max'}
            else: result={'numbers':[random.randint(mn,mx) for _ in range(count)],'min':mn,'max':mx,'count':count}
        except: result={'error':'Please enter valid numbers'}
    related = [t for t in TOOLS if t['category']=='calculators' and t['slug']!='random-number'][:4]
    return render_template('tools/random_number.html',
        title="Random Number Generator - Free Online | ANS Tools",
        description="Generate random numbers online for free. Set min, max range and quantity.",
        keywords="random number generator",
        canonical="https://anstools.xyz/tools/random-number",
        result=result, related=related, slug='random-number')

@app.route('/tools/emi-calculator', methods=['GET','POST'])
def emi_calculator():
    track_view('emi-calculator')
    result = None
    if request.method == 'POST':
        track_use('emi-calculator')
        try:
            principal = float(request.form.get('principal',0))
            rate = float(request.form.get('rate',0))
            tenure = int(request.form.get('tenure',0))
            if principal<=0 or rate<=0 or tenure<=0:
                result={'error':'Please enter valid positive values'}
            else:
                r = rate/12/100
                emi = principal*r*(1+r)**tenure/((1+r)**tenure-1)
                total = emi*tenure
                schedule = []
                balance = principal
                for m in range(1,min(tenure+1,13)):
                    ip = balance*r; pp = emi-ip; balance-=pp
                    schedule.append({'month':m,'emi':round(emi,2),'principal':round(pp,2),'interest':round(ip,2),'balance':round(max(balance,0),2)})
                result={'emi':round(emi,2),'total_payment':round(total,2),'total_interest':round(total-principal,2),'principal':principal,'schedule':schedule}
        except: result={'error':'Please enter valid numbers'}
    related = [t for t in TOOLS if t['category']=='calculators' and t['slug']!='emi-calculator'][:4]
    return render_template('tools/emi_calculator.html',
        title="EMI Calculator - Free Online | ANS Tools",
        description="Calculate loan EMI online for free. Get monthly installment, total interest, and amortization schedule.",
        keywords="emi calculator, loan emi calculator",
        canonical="https://anstools.xyz/tools/emi-calculator",
        result=result, related=related, slug='emi-calculator')

@app.route('/tools/tip-calculator', methods=['GET','POST'])
def tip_calculator():
    track_view('tip-calculator')
    result = None
    if request.method == 'POST':
        track_use('tip-calculator')
        try:
            bill = float(request.form.get('bill',0))
            tip_pct = float(request.form.get('tip_percent',15))
            people = int(request.form.get('people',1))
            if bill<=0: result={'error':'Enter valid bill amount'}
            elif people<=0: result={'error':'People must be at least 1'}
            else:
                tip = bill*(tip_pct/100)
                total = bill+tip
                result={'bill':round(bill,2),'tip_percent':tip_pct,'tip_amount':round(tip,2),'total_bill':round(total,2),'tip_per_person':round(tip/people,2),'total_per_person':round(total/people,2),'people':people}
        except: result={'error':'Please enter valid numbers'}
    related = [t for t in TOOLS if t['category']=='calculators' and t['slug']!='tip-calculator'][:4]
    return render_template('tools/tip_calculator.html',
        title="Tip Calculator - Free Online | ANS Tools",
        description="Calculate tip and split bill online for free. Find tip amount per person instantly.",
        keywords="tip calculator, bill splitter",
        canonical="https://anstools.xyz/tools/tip-calculator",
        result=result, related=related, slug='tip-calculator')

@app.route('/tools/invoice-generator', methods=['GET','POST'])
def invoice_generator():
    track_view('invoice-generator')
    result = None
    if request.method == 'POST':
        track_use('invoice-generator')
        try:
            biz_name = request.form.get('biz_name','Your Business')
            biz_address = request.form.get('biz_address','')
            biz_email = request.form.get('biz_email','')
            client_name = request.form.get('client_name','Client')
            client_address = request.form.get('client_address','')
            invoice_no = request.form.get('invoice_no','INV-001')
            invoice_date = request.form.get('invoice_date', date.today().isoformat())
            due_date = request.form.get('due_date','')
            tax_rate = float(request.form.get('tax_rate',0))
            items_desc = request.form.getlist('item_desc')
            items_qty = request.form.getlist('item_qty')
            items_price = request.form.getlist('item_price')
            items = []
            subtotal = 0
            for i in range(len(items_desc)):
                if items_desc[i].strip():
                    qty = float(items_qty[i]) if i<len(items_qty) else 1
                    price = float(items_price[i]) if i<len(items_price) else 0
                    total_line = qty*price
                    subtotal += total_line
                    items.append({'desc':items_desc[i],'qty':qty,'price':price,'total':total_line})
            tax = subtotal*tax_rate/100
            grand_total = subtotal+tax
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font('Helvetica','B',20)
            pdf.set_text_color(37,99,235)
            pdf.cell(0,12,biz_name,ln=True)
            pdf.set_font('Helvetica','',10); pdf.set_text_color(100,116,139)
            if biz_address: pdf.cell(0,6,biz_address,ln=True)
            if biz_email: pdf.cell(0,6,biz_email,ln=True)
            pdf.ln(6)
            pdf.set_font('Helvetica','B',16); pdf.set_text_color(15,23,42)
            pdf.cell(0,10,'INVOICE',ln=True)
            pdf.set_font('Helvetica','',10); pdf.set_text_color(100,116,139)
            pdf.cell(0,6,f'Invoice No: {invoice_no}',ln=True)
            pdf.cell(0,6,f'Date: {invoice_date}',ln=True)
            if due_date: pdf.cell(0,6,f'Due: {due_date}',ln=True)
            pdf.ln(6)
            pdf.set_font('Helvetica','B',11); pdf.set_text_color(15,23,42)
            pdf.cell(0,7,f'Bill To: {client_name}',ln=True)
            if client_address: pdf.set_font('Helvetica','',10); pdf.set_text_color(100,116,139); pdf.cell(0,6,client_address,ln=True)
            pdf.ln(8)
            pdf.set_fill_color(37,99,235); pdf.set_text_color(255,255,255); pdf.set_font('Helvetica','B',10)
            pdf.cell(90,8,'Description',fill=True); pdf.cell(25,8,'Qty',fill=True,align='C')
            pdf.cell(35,8,'Unit Price',fill=True,align='R'); pdf.cell(40,8,'Total',fill=True,align='R',ln=True)
            pdf.set_text_color(15,23,42); pdf.set_font('Helvetica','',10)
            for idx,item in enumerate(items):
                fill = idx%2==0
                if fill: pdf.set_fill_color(248,250,252)
                pdf.cell(90,7,item['desc'],fill=fill)
                pdf.cell(25,7,str(item['qty']),fill=fill,align='C')
                pdf.cell(35,7,f"${item['price']:.2f}",fill=fill,align='R')
                pdf.cell(40,7,f"${item['total']:.2f}",fill=fill,align='R',ln=True)
            pdf.ln(4)
            pdf.set_font('Helvetica','',10)
            pdf.cell(150,7,'Subtotal:',align='R'); pdf.cell(40,7,f'${subtotal:.2f}',align='R',ln=True)
            if tax_rate>0:
                pdf.cell(150,7,f'Tax ({tax_rate}%):',align='R'); pdf.cell(40,7,f'${tax:.2f}',align='R',ln=True)
            pdf.set_font('Helvetica','B',11)
            pdf.cell(150,8,'Total:',align='R'); pdf.cell(40,8,f'${grand_total:.2f}',align='R',ln=True)
            b64 = base64.b64encode(bytes(pdf.output())).decode()
            result = {'b64':b64,'invoice_no':invoice_no,'total':f'{grand_total:.2f}'}
        except Exception as e:
            result = {'error': str(e)}
    related = [t for t in TOOLS if t['category']=='pdf' and t['slug']!='invoice-generator'][:4]
    return render_template('tools/invoice_generator.html',
        title="Invoice Generator - Free Online | ANS Tools",
        description="Generate professional PDF invoices online for free. Add items, calculate tax, download instantly.",
        keywords="invoice generator, create invoice online, pdf invoice",
        canonical="https://anstools.xyz/tools/invoice-generator",
        result=result, related=related, slug='invoice-generator', today=date.today().isoformat())

# ── Downloaders ───────────────────────────────────────────────────────────────
@app.route('/tools/tiktok-downloader', methods=['GET','POST'])
def tiktok_downloader():
    track_view('tiktok-downloader')
    result = None
    if request.method == 'POST':
        track_use('tiktok-downloader')
        video_url = request.form.get('url','').strip()
        if video_url:
            try:
                headers = {"x-rapidapi-key": os.environ.get("RAPIDAPI_KEY","PASTE_YOUR_RAPIDAPI_KEY_HERE"),
                           "x-rapidapi-host": "tiktok-video-no-watermark2.p.rapidapi.com"}
                resp = requests.get("https://tiktok-video-no-watermark2.p.rapidapi.com/",
                                    headers=headers, params={"url":video_url,"hd":"1"}, timeout=15)
                data = resp.json()
                if data.get('data') and data['data'].get('play'):
                    result = {'video_url':data['data']['play'],
                              'thumbnail':data['data'].get('cover',''),
                              'title':data['data'].get('title','TikTok Video'),
                              'author':data['data'].get('author',{}).get('nickname','')}
                else:
                    result = {'error':'Could not fetch video. Please check the URL or configure your RapidAPI key.'}
            except: result = {'error':'Failed to download. Please verify the URL.'}
        else: result = {'error':'Please enter a TikTok video URL'}
    related = [t for t in TOOLS if t['slug'] in ('instagram-downloader','youtube-thumbnail','qr-generator','image-compressor')]
    return render_template('tools/tiktok_downloader.html',
        title="TikTok Video Downloader Without Watermark - ANS Tools",
        description="Download TikTok videos without watermark in HD quality. Free, fast, no signup required.",
        keywords="tiktok downloader, download tiktok video, tiktok without watermark",
        canonical="https://anstools.xyz/tools/tiktok-downloader",
        result=result, related=related, slug='tiktok-downloader')

@app.route('/tools/instagram-downloader', methods=['GET','POST'])
def instagram_downloader():
    track_view('instagram-downloader')
    result = None
    if request.method == 'POST':
        track_use('instagram-downloader')
        post_url = request.form.get('url','').strip()
        if post_url:
            try:
                headers = {"x-rapidapi-key": os.environ.get("RAPIDAPI_KEY","PASTE_YOUR_RAPIDAPI_KEY_HERE"),
                           "x-rapidapi-host": "instagram-downloader-download-instagram-videos-stories.p.rapidapi.com"}
                resp = requests.get("https://instagram-downloader-download-instagram-videos-stories.p.rapidapi.com/index",
                                    headers=headers, params={"url":post_url}, timeout=15)
                data = resp.json()
                if data.get('media'):
                    result = {'media_url':data['media'],'type':data.get('type','video'),'thumbnail':data.get('thumbnail','')}
                else:
                    result = {'error':'Could not fetch media. Please check the URL or configure your RapidAPI key.'}
            except: result = {'error':'Failed to download. Please verify the URL.'}
        else: result = {'error':'Please enter an Instagram URL'}
    related = [t for t in TOOLS if t['slug'] in ('tiktok-downloader','youtube-thumbnail','qr-generator','image-compressor')]
    return render_template('tools/instagram_downloader.html',
        title="Instagram Downloader - Photos, Reels & Stories | ANS Tools",
        description="Download Instagram photos, Reels and Stories online for free. No watermark. No signup required.",
        keywords="instagram downloader, download instagram video, instagram reels downloader",
        canonical="https://anstools.xyz/tools/instagram-downloader",
        result=result, related=related, slug='instagram-downloader')

@app.route('/tools/youtube-thumbnail', methods=['GET','POST'])
def youtube_thumbnail():
    track_view('youtube-thumbnail')
    result = None
    if request.method == 'POST':
        track_use('youtube-thumbnail')
        url = request.form.get('url','').strip()
        if url:
            video_id = None
            patterns = [
                r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})',
            ]
            for p in patterns:
                m = re.search(p, url)
                if m: video_id = m.group(1); break
            if video_id:
                result = {
                    'video_id': video_id,
                    'maxres': f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg',
                    'hq': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
                    'mq': f'https://img.youtube.com/vi/{video_id}/mqdefault.jpg',
                    'sd': f'https://img.youtube.com/vi/{video_id}/sddefault.jpg',
                }
            else:
                result = {'error': 'Could not extract video ID. Please paste a valid YouTube URL.'}
        else:
            result = {'error': 'Please enter a YouTube video URL'}
    related = [t for t in TOOLS if t['slug'] in ('tiktok-downloader','instagram-downloader','image-compressor','qr-generator')]
    return render_template('tools/youtube_thumbnail.html',
        title="YouTube Thumbnail Downloader - Free HD | ANS Tools",
        description="Download YouTube video thumbnails in HD quality for free. Get maxresdefault, hqdefault thumbnails instantly.",
        keywords="youtube thumbnail downloader, download youtube thumbnail, yt thumbnail",
        canonical="https://anstools.xyz/tools/youtube-thumbnail",
        result=result, related=related, slug='youtube-thumbnail')

# ── New Text/Dev Tools ────────────────────────────────────────────────────────
@app.route('/tools/json-formatter', methods=['GET','POST'])
def json_formatter():
    track_view('json-formatter')
    result = None
    if request.method == 'POST':
        track_use('json-formatter')
        raw = request.form.get('json','').strip()
        action = request.form.get('action','format')
        if raw:
            try:
                parsed = json.loads(raw)
                if action == 'format':
                    output = json.dumps(parsed, indent=2, ensure_ascii=False)
                    result = {'output': output, 'valid': True, 'action': 'formatted', 'keys': len(parsed) if isinstance(parsed,(dict,list)) else 1}
                elif action == 'minify':
                    output = json.dumps(parsed, separators=(',',':'), ensure_ascii=False)
                    result = {'output': output, 'valid': True, 'action': 'minified'}
                elif action == 'validate':
                    result = {'valid': True, 'action': 'validated', 'type': type(parsed).__name__,
                              'keys': len(parsed) if isinstance(parsed,dict) else len(parsed) if isinstance(parsed,list) else 1}
            except json.JSONDecodeError as e:
                result = {'error': f'Invalid JSON: {e}', 'valid': False}
        else:
            result = {'error': 'Please enter JSON data'}
    related = [t for t in TOOLS if t['slug'] in ('base64','url-encoder','meta-tag-generator','word-counter')]
    return render_template('tools/json_formatter.html',
        title="JSON Formatter & Validator - Free Online | ANS Tools",
        description="Format, validate and beautify JSON data online for free. Pretty print or minify JSON instantly.",
        keywords="json formatter, json validator, json beautifier, format json online",
        canonical="https://anstools.xyz/tools/json-formatter",
        result=result, related=related, slug='json-formatter')

def count_syllables(word):
    word = word.lower().strip(".,!?;:'\"")
    if len(word) <= 2: return 1
    count = len(re.findall(r'[aeiou]+', word))
    if word.endswith('e') and count > 1: count -= 1
    return max(1, count)

@app.route('/tools/readability-checker', methods=['GET','POST'])
def readability_checker():
    track_view('readability-checker')
    result = None
    if request.method == 'POST':
        track_use('readability-checker')
        text = request.form.get('text','').strip()
        if text:
            sentences = max(1, len(re.findall(r'[.!?]+', text)))
            words_list = re.findall(r'\b[a-zA-Z]+\b', text)
            word_count = max(1, len(words_list))
            syllable_count = sum(count_syllables(w) for w in words_list)
            complex_words = sum(1 for w in words_list if count_syllables(w) >= 3)
            asl = word_count / sentences  # avg sentence length
            asw = syllable_count / word_count  # avg syllables per word
            # Flesch Reading Ease
            fre = round(206.835 - 1.015*asl - 84.6*asw, 1)
            fre = max(0, min(100, fre))
            # Flesch-Kincaid Grade Level
            fkgl = round(0.39*asl + 11.8*asw - 15.59, 1)
            fkgl = max(0, fkgl)
            # Gunning Fog
            fog = round(0.4*(asl + 100*(complex_words/word_count)), 1)
            if fre >= 90: ease = 'Very Easy'; grade_label = '5th grade'
            elif fre >= 80: ease = 'Easy'; grade_label = '6th grade'
            elif fre >= 70: ease = 'Fairly Easy'; grade_label = '7th grade'
            elif fre >= 60: ease = 'Standard'; grade_label = '8th-9th grade'
            elif fre >= 50: ease = 'Fairly Difficult'; grade_label = '10th-12th grade'
            elif fre >= 30: ease = 'Difficult'; grade_label = 'College level'
            else: ease = 'Very Difficult'; grade_label = 'College graduate'
            result = {
                'words': word_count, 'sentences': sentences,
                'syllables': syllable_count, 'complex_words': complex_words,
                'fre': fre, 'fkgl': fkgl, 'fog': fog,
                'ease': ease, 'grade_label': grade_label,
                'avg_sentence_length': round(asl, 1),
                'avg_syllables_per_word': round(asw, 2),
            }
        else:
            result = {'error': 'Please enter some text to analyze'}
    related = [t for t in TOOLS if t['slug'] in ('word-counter','text-diff','case-converter','meta-tag-generator')]
    return render_template('tools/readability_checker.html',
        title="Readability Checker - Flesch-Kincaid Score | ANS Tools",
        description="Check text readability online for free. Get Flesch Reading Ease, Flesch-Kincaid Grade Level and Gunning Fog scores.",
        keywords="readability checker, flesch kincaid, readability score, reading level checker",
        canonical="https://anstools.xyz/tools/readability-checker",
        result=result, related=related, slug='readability-checker')

@app.route('/tools/text-diff', methods=['GET','POST'])
def text_diff():
    track_view('text-diff')
    result = None
    if request.method == 'POST':
        track_use('text-diff')
        text1 = request.form.get('text1','')
        text2 = request.form.get('text2','')
        if text1 or text2:
            lines1 = text1.splitlines(keepends=True)
            lines2 = text2.splitlines(keepends=True)
            diff = list(difflib.unified_diff(lines1, lines2, fromfile='Text A', tofile='Text B', lineterm=''))
            # HTML diff
            html_diff = difflib.HtmlDiff(wrapcolumn=80)
            table = html_diff.make_table(lines1, lines2, fromdesc='Text A', todesc='Text B', context=True, numlines=3)
            additions = sum(1 for l in diff if l.startswith('+') and not l.startswith('+++'))
            deletions = sum(1 for l in diff if l.startswith('-') and not l.startswith('---'))
            result = {
                'diff': '\n'.join(diff),
                'table': table,
                'additions': additions,
                'deletions': deletions,
                'has_diff': bool(diff),
                'text1_lines': len(lines1),
                'text2_lines': len(lines2),
            }
        else:
            result = {'error': 'Please enter text in both fields'}
    related = [t for t in TOOLS if t['slug'] in ('word-counter','readability-checker','case-converter','base64')]
    return render_template('tools/text_diff.html',
        title="Text Diff Checker - Compare Two Texts | ANS Tools",
        description="Compare two texts online for free. Find differences, additions, and deletions between texts instantly.",
        keywords="text diff, compare text online, text difference checker",
        canonical="https://anstools.xyz/tools/text-diff",
        result=result, related=related, slug='text-diff')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
