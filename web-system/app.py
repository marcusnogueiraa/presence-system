from flask import Flask, render_template, request, redirect, url_for, jsonify, Response, session, flash
import sqlite3
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from io import BytesIO
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'  # Change to a strong secret key
socketio = SocketIO(app, cors_allowed_origins="*")
DATABASE = 'database.db'

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Por favor, faça login para acessar esta página.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def criar_tabelas():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Admin table
    c.execute('''CREATE TABLE IF NOT EXISTS administradores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT)''')
    
    # Classes table
    c.execute('''CREATE TABLE IF NOT EXISTS turmas (
                id TEXT PRIMARY KEY,
                nome_turma TEXT,
                professor TEXT,
                sala TEXT)''')
    
    # Students table (updated structure)
    c.execute('''CREATE TABLE IF NOT EXISTS alunos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                matricula TEXT UNIQUE NOT NULL,
                rfid TEXT UNIQUE,
                foto TEXT,
                email TEXT,
                telefone TEXT,
                data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Student-Class relationship table
    c.execute('''CREATE TABLE IF NOT EXISTS aluno_turma (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                aluno_id INTEGER NOT NULL,
                turma_id TEXT NOT NULL,
                data_inscricao DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(aluno_id) REFERENCES alunos(id) ON DELETE CASCADE,
                FOREIGN KEY(turma_id) REFERENCES turmas(id) ON DELETE CASCADE,
                UNIQUE(aluno_id, turma_id))''')
    
    # Attendance table
    c.execute('''CREATE TABLE IF NOT EXISTS presencas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                aluno_id INTEGER NOT NULL,
                turma_id TEXT NOT NULL,
                data_hora DATETIME NOT NULL,
                FOREIGN KEY(aluno_id) REFERENCES alunos(id) ON DELETE CASCADE,
                FOREIGN KEY(turma_id) REFERENCES turmas(id) ON DELETE CASCADE)''')
    
    # Create default admin if not exists
    c.execute("SELECT id FROM administradores WHERE username = 'admin'")
    if not c.fetchone():
        senha_hash = generate_password_hash('admin123')
        c.execute("INSERT INTO administradores (username, password) VALUES (?, ?)",
                 ('admin', senha_hash))
    
    conn.commit()
    conn.close()

def migrar_dados():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    try:
        # Check if old structure exists
        c.execute("PRAGMA table_info(alunos)")
        columns = [info[1] for info in c.fetchall()]
        
        if 'turma_id' in columns:
            # Migrate data to new structure
            c.execute('''
                INSERT INTO aluno_turma (aluno_id, turma_id)
                SELECT id, turma_id FROM alunos WHERE turma_id IS NOT NULL
            ''')
            
            # Create new table without turma_id
            c.execute('''
                CREATE TABLE alunos_nova AS
                SELECT id, nome, matricula, rfid, foto, email, telefone, data_cadastro
                FROM alunos
            ''')
            
            c.execute('DROP TABLE alunos')
            c.execute('ALTER TABLE alunos_nova RENAME TO alunos')
            
            conn.commit()
            print("Migration completed successfully!")
    except Exception as e:
        conn.rollback()
        print(f"Migration error: {e}")
    finally:
        conn.close()

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT * FROM administradores WHERE username = ?", (username,))
        admin = c.fetchone()
        conn.close()
        
        if admin and check_password_hash(admin['password'], password):
            session['logged_in'] = True
            session['username'] = username
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

# Main routes
@app.route('/')
@login_required
def index():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('''
        SELECT t.id, t.nome_turma, t.professor, t.sala, 
        COUNT(at.aluno_id) as total_alunos
        FROM turmas t
        LEFT JOIN aluno_turma at ON t.id = at.turma_id
        GROUP BY t.id
    ''')
    turmas = c.fetchall()
    
    conn.close()
    return render_template('index.html', turmas=turmas)

@app.route('/turma/<turma_id>/relatorio')
@login_required
def relatorio_turma(turma_id):
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    turma = c.execute("SELECT * FROM turmas WHERE id = ?", (turma_id,)).fetchone()
    
    c.execute('''
        SELECT a.nome, p.data_hora 
        FROM presencas p
        JOIN alunos a ON p.aluno_id = a.id
        WHERE p.turma_id = ?
        ORDER BY p.data_hora DESC
    ''', (turma_id,))
    presencas = c.fetchall()
    conn.close()
    
    # Process data for report
    presencas_por_data = {}
    alunos_por_data = {}
    
    for presenca in presencas:
        date = presenca['data_hora'].split()[0]
        
        if date not in presencas_por_data:
            presencas_por_data[date] = []
            alunos_por_data[date] = set()
        
        if presenca['nome'] not in alunos_por_data[date]:
            presencas_por_data[date].append(presenca)
            alunos_por_data[date].add(presenca['nome'])
    
    sorted_dates = sorted(presencas_por_data.keys(), reverse=True)
    
    # Generate PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'title',
        parent=styles['Heading1'],
        alignment=1,
        spaceAfter=20
    )
    
    date_style = ParagraphStyle(
        'date',
        parent=styles['Heading2'],
        spaceAfter=10
    )
    
    elements = []
    elements.append(Paragraph(f"Relatório de Presença - {turma['nome_turma']}", title_style))
    elements.append(Paragraph(f"Professor: {turma['professor']}", styles['Normal']))
    elements.append(Paragraph(f"Sala: {turma['sala']}", styles['Normal']))
    elements.append(Spacer(1, 30))
    
    for date in sorted_dates:
        elements.append(Paragraph(date, date_style))
        
        students = sorted(presencas_por_data[date], key=lambda p: p['nome'])
        table_data = [["Aluno"]]
        
        for presenca in students:
            table_data.append([presenca['nome']])
        
        table = Table(table_data, colWidths=[400])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.white),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 15))
    
    doc.build(elements)
    buffer.seek(0)
    
    return Response(
        buffer,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=relatorio_{turma["nome_turma"]}.pdf'}
    )

# Class management
@app.route('/nova_turma', methods=['GET', 'POST'])
@login_required
def nova_turma():
    if request.method == 'POST':
        turma_id = str(uuid.uuid4())
        nome_turma = request.form['nome_turma']
        professor = request.form['professor']
        sala = request.form['sala']
        
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("INSERT INTO turmas (id, nome_turma, professor, sala) VALUES (?, ?, ?, ?)",
                 (turma_id, nome_turma, professor, sala))
        conn.commit()
        conn.close()
        
        return redirect(url_for('index'))
    
    return render_template('nova_turma.html')

@app.route('/turma/<turma_id>')
@login_required
def turma_detail(turma_id):
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    
    turma = conn.execute("SELECT * FROM turmas WHERE id = ?", (turma_id,)).fetchone()
    
    if not turma:
        conn.close()
        return "Turma não encontrada", 404
    
    # Get class students
    alunos_turma = conn.execute('''
        SELECT a.id, a.nome, a.matricula, a.rfid
        FROM aluno_turma at
        JOIN alunos a ON at.aluno_id = a.id
        WHERE at.turma_id = ?
        ORDER BY a.nome
    ''', (turma_id,)).fetchall()
    
    # Get available students to add
    alunos_disponiveis = conn.execute('''
        SELECT a.id, a.nome, a.matricula
        FROM alunos a
        WHERE a.id NOT IN (
            SELECT aluno_id FROM aluno_turma WHERE turma_id = ?
        )
        ORDER BY a.nome
    ''', (turma_id,)).fetchall()
    
    # Get class attendance
    presencas = conn.execute('''
        SELECT a.nome, a.matricula, p.data_hora 
        FROM presencas p
        JOIN alunos a ON p.aluno_id = a.id
        WHERE p.turma_id = ?
        ORDER BY p.data_hora DESC
    ''', (turma_id,)).fetchall()
    
    conn.close()
    
    return render_template('turmas/detalhes.html', 
                         turma=turma, 
                         alunos_turma=alunos_turma,
                         alunos_disponiveis=alunos_disponiveis,
                         presencas=presencas)

@app.route('/excluir_turma/<turma_id>', methods=['POST'])
@login_required
def excluir_turma(turma_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute("DELETE FROM aluno_turma WHERE turma_id = ?", (turma_id,))
    c.execute("DELETE FROM presencas WHERE turma_id = ?", (turma_id,))
    c.execute("DELETE FROM turmas WHERE id = ?", (turma_id,))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('index'))

# Student management
@app.route('/alunos')
@login_required
def listar_alunos():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    search = request.args.get('busca', '')
    
    if search:
        c.execute('''
            SELECT * FROM alunos 
            WHERE nome LIKE ? OR matricula LIKE ? OR rfid LIKE ?
            ORDER BY nome
        ''', (f'%{search}%', f'%{search}%', f'%{search}%'))
    else:
        c.execute('SELECT * FROM alunos ORDER BY nome')
    
    alunos = c.fetchall()
    conn.close()
    return render_template('alunos/lista.html', alunos=alunos, busca=search)

@app.route('/alunos/novo', methods=['GET', 'POST'])
@login_required
def novo_aluno():
    if request.method == 'POST':
        nome = request.form['nome']
        matricula = request.form['matricula']
        rfid = request.form.get('rfid', '')
        email = request.form.get('email', '')
        telefone = request.form.get('telefone', '')
        
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        try:
            c.execute('''
                INSERT INTO alunos (nome, matricula, rfid, email, telefone)
                VALUES (?, ?, ?, ?, ?)
            ''', (nome, matricula, rfid, email, telefone))
            conn.commit()
            flash('Aluno cadastrado com sucesso!', 'success')
            return redirect(url_for('listar_alunos'))
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if 'matricula' in str(e):
                flash('Matrícula já cadastrada!', 'danger')
            elif 'rfid' in str(e):
                flash('RFID já cadastrado!', 'danger')
        finally:
            conn.close()
    
    return render_template('alunos/novo.html')

@app.route('/alunos/<int:aluno_id>')
@login_required
def detalhes_aluno(aluno_id):
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    aluno = c.execute('SELECT * FROM alunos WHERE id = ?', (aluno_id,)).fetchone()
    
    if not aluno:
        flash('Aluno não encontrado!', 'danger')
        return redirect(url_for('listar_alunos'))
    
    # Get student's classes
    c.execute('''
        SELECT t.id, t.nome_turma, t.professor, t.sala, at.data_inscricao
        FROM aluno_turma at
        JOIN turmas t ON at.turma_id = t.id
        WHERE at.aluno_id = ?
        ORDER BY t.nome_turma
    ''', (aluno_id,))
    turmas = c.fetchall()
    
    # Get student's attendance
    c.execute('''
        SELECT p.data_hora, t.nome_turma, t.sala
        FROM presencas p
        JOIN turmas t ON p.turma_id = t.id
        WHERE p.aluno_id = ?
        ORDER BY p.data_hora DESC
        LIMIT 10
    ''', (aluno_id,))
    presencas = c.fetchall()
    
    # Statistics
    c.execute('SELECT COUNT(*) FROM presencas WHERE aluno_id = ?', (aluno_id,))
    total_presencas = c.fetchone()[0]
    
    c.execute('SELECT COUNT(DISTINCT turma_id) FROM aluno_turma WHERE aluno_id = ?', (aluno_id,))
    total_turmas = c.fetchone()[0]
    
    conn.close()
    
    return render_template('alunos/detalhes.html', 
                         aluno=aluno, 
                         turmas=turmas, 
                         presencas=presencas,
                         total_presencas=total_presencas,
                         total_turmas=total_turmas)

@app.route('/alunos/<int:aluno_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_aluno(aluno_id):
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    aluno = c.execute('SELECT * FROM alunos WHERE id = ?', (aluno_id,)).fetchone()
    
    if not aluno:
        conn.close()
        flash('Aluno não encontrado!', 'danger')
        return redirect(url_for('listar_alunos'))
    
    if request.method == 'POST':
        nome = request.form['nome']
        matricula = request.form['matricula']
        rfid = request.form.get('rfid', '')
        email = request.form.get('email', '')
        telefone = request.form.get('telefone', '')
        
        try:
            c.execute('''
                UPDATE alunos 
                SET nome = ?, matricula = ?, rfid = ?, email = ?, telefone = ?
                WHERE id = ?
            ''', (nome, matricula, rfid, email, telefone, aluno_id))
            conn.commit()
            flash('Dados do aluno atualizados com sucesso!', 'success')
            return redirect(url_for('detalhes_aluno', aluno_id=aluno_id))
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if 'matricula' in str(e):
                flash('Matrícula já cadastrada!', 'danger')
            elif 'rfid' in str(e):
                flash('RFID já cadastrado!', 'danger')
    
    conn.close()
    return render_template('alunos/editar.html', aluno=aluno)

@app.route('/alunos/<int:aluno_id>/excluir', methods=['POST'])
@login_required
def excluir_aluno(aluno_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    try:
        c.execute('DELETE FROM alunos WHERE id = ?', (aluno_id,))
        conn.commit()
        flash('Aluno excluído com sucesso!', 'success')
    except Exception as e:
        conn.rollback()
        flash('Erro ao excluir aluno!', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('listar_alunos'))

# Class-student relationship
@app.route('/turmas/<turma_id>/adicionar-aluno', methods=['POST'])
@login_required
def adicionar_aluno_turma(turma_id):
    aluno_id = request.form.get('aluno_id')
    
    if not aluno_id:
        flash('Selecione um aluno para adicionar à turma', 'danger')
        return redirect(url_for('turma_detail', turma_id=turma_id))
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    try:
        c.execute('''
            INSERT INTO aluno_turma (aluno_id, turma_id)
            VALUES (?, ?)
        ''', (aluno_id, turma_id))
        conn.commit()
        flash('Aluno adicionado à turma com sucesso!', 'success')
    except sqlite3.IntegrityError:
        conn.rollback()
        flash('Este aluno já está na turma!', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('turma_detail', turma_id=turma_id))

@app.route('/turmas/<turma_id>/remover-aluno/<int:aluno_id>', methods=['POST'])
@login_required
def remover_aluno_turma(turma_id, aluno_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    try:
        c.execute('''
            DELETE FROM aluno_turma 
            WHERE aluno_id = ? AND turma_id = ?
        ''', (aluno_id, turma_id))
        conn.commit()
        flash('Aluno removido da turma com sucesso!', 'success')
    except Exception as e:
        conn.rollback()
        flash('Erro ao remover aluno da turma!', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('turma_detail', turma_id=turma_id))

# API routes
@app.route('/api/registrar_presenca', methods=['POST'])
def registrar_presenca_api():
    data = request.get_json()
    rfid = data.get('rfid')
    turma_uuid = data.get('uuid')
    
    if not rfid or not turma_uuid:
        return jsonify({'status': 'error', 'message': 'Dados faltando'}), 400
    
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Check if student is in class
    aluno = c.execute('''
        SELECT a.id, a.nome, a.matricula 
        FROM alunos a
        JOIN aluno_turma at ON a.id = at.aluno_id
        WHERE a.rfid = ? AND at.turma_id = ?
    ''', (rfid, turma_uuid)).fetchone()
    
    if aluno:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('''
            INSERT INTO presencas (aluno_id, turma_id, data_hora)
            VALUES (?, ?, ?)
        ''', (aluno['id'], turma_uuid, now))
        conn.commit()
        conn.close()

        socketio.emit('nova_presenca', {
            'aluno': aluno['nome'],
            'turma': turma_uuid,
            'hora': now,
            'matricula': aluno['matricula']
        })
        
        return jsonify({'status': 'success', 'message': 'Presença registrada'}), 200
    
    conn.close()
    return jsonify({'status': 'error', 'message': 'Aluno não encontrado ou não está na turma'}), 404

@app.route('/api/ajuda')
@login_required
def api_ajuda():
    return render_template('api_ajuda.html')

if __name__ == '__main__':
    criar_tabelas()
    migrar_dados()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)