from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from groq import Groq
import uuid

app = Flask(__name__)
app.secret_key = "secret123"

import os
from dotenv import load_dotenv
load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def get_db():
    conn = sqlite3.connect('study_assistant.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        query TEXT NOT NULL,
        response TEXT NOT NULL,
        output_type TEXT NOT NULL,
        chat_session_id TEXT,
        chat_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.commit()
    db.close()

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=? AND password=?',
                          (username, password)).fetchone()
        db.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['chat_history'] = []
            session['current_chat_id'] = None
            return redirect(url_for('dashboard'))
        else:
            error = "Wrong username or password!"
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        try:
            db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            db.commit()
            db.close()
            return redirect(url_for('login'))
        except:
            error = "Username already exists!"
            db.close()
    return render_template('register.html', error=error)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if 'chat_history' not in session:
        session['chat_history'] = []
    if 'current_chat_id' not in session:
        session['current_chat_id'] = None

    if request.method == 'POST':

        if request.form.get('clear_chat'):
            session['chat_history'] = []
            session['current_chat_id'] = None
            session.modified = True
            return redirect(url_for('dashboard'))

        if request.form.get('new_chat'):
            session['chat_history'] = []
            session['current_chat_id'] = None
            session.modified = True
            return redirect(url_for('dashboard'))

        topic = request.form['topic']
        output_type = request.form['output_type']

        if not session.get('current_chat_id'):
            session['current_chat_id'] = str(uuid.uuid4())[:8]

        if output_type == 'summary':
            prompt = (
                f"Give a well-structured summary of: {topic}\n\n"
                "Format with:\n"
                "- A clear ## Overview heading\n"
                "- Key points as bullet list\n"
                "- A ## Key Takeaways section at the end\n"
                "Be concise but thorough."
            )
        elif output_type == 'explanation':
            prompt = (
                f"Explain this topic clearly: {topic}\n\n"
                "Format with:\n"
                "- Start with a simple one-line definition\n"
                "- Use numbered steps or sections if applicable\n"
                "- Include a real-world example\n"
                "- End with a ## Summary line\n"
                "Write for a student audience."
            )
        elif output_type == 'mcq':
            prompt = (
                f"Create 5 MCQ questions about: {topic}\n\n"
                "Format each question exactly like this:\n"
                "Q1. [Question text]\n"
                "A) [Option]\n"
                "B) [Option]\n"
                "C) [Option]\n"
                "D) [Option]\n"
                "Answer: [Letter]\n\n"
                "Make questions progressively harder."
            )
        elif output_type == 'code':
            prompt = (
                f"Write clean, well-commented code for: {topic}\n\n"
                "Format your response as:\n"
                "- Brief explanation of what the code does\n"
                "- The complete code in a code block\n"
                "- Step-by-step explanation of how it works\n"
                "- Example output if applicable\n"
                "Use best practices."
            )
        elif output_type == 'factcheck':
            prompt = (
                f"Fact-check the following claim or topic: {topic}\n\n"
                "Format your response as:\n"
                "## Verdict\n"
                "[TRUE / FALSE / PARTIALLY TRUE / UNVERIFIABLE]\n\n"
                "## Analysis\n"
                "[Detailed analysis]\n\n"
                "## Key Facts\n"
                "[Bullet points of verified facts]\n\n"
                "## Sources to Check\n"
                "[Suggest reliable sources]\n"
                "Be objective and evidence-based."
            )
        else:
            prompt = topic

        messages = [{"role": "system", "content": (
            "You are Qasim, a friendly and highly knowledgeable AI study assistant. "
            "Always format your responses clearly using markdown. "
            "Be accurate, educational, and engaging."
        )}]

        for chat in session['chat_history']:
            messages.append({"role": "user", "content": chat['user']})
            messages.append({"role": "assistant", "content": chat['ai']})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages
        )
        ai_response = response.choices[0].message.content

        session['chat_history'].append({
            'user': topic,
            'type': output_type,
            'ai': ai_response
        })
        session.modified = True

        chat_name = session['chat_history'][0]['user'][:45]

        db = get_db()
        db.execute(
            'INSERT INTO history (user_id, query, response, output_type, chat_session_id, chat_name) VALUES (?,?,?,?,?,?)',
            (session['user_id'], topic, ai_response, output_type, session['current_chat_id'], chat_name)
        )
        db.commit()
        db.close()

    db = get_db()
    records = db.execute('''
        SELECT *, MAX(created_at) as last_time
        FROM history WHERE user_id=?
        GROUP BY chat_session_id
        ORDER BY last_time DESC
    ''', (session['user_id'],)).fetchall()
    db.close()

    return render_template('dashboard.html',
                           chat_history=session.get('chat_history', []),
                           records=records,
                           current_chat_id=session.get('current_chat_id'))

@app.route('/load_chat/<chat_session_id>')
def load_chat(chat_session_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    chats = db.execute(
        'SELECT * FROM history WHERE user_id=? AND chat_session_id=? ORDER BY created_at ASC',
        (session['user_id'], chat_session_id)
    ).fetchall()
    db.close()
    session['chat_history'] = [{'user': c['query'], 'type': c['output_type'], 'ai': c['response']} for c in chats]
    session['current_chat_id'] = chat_session_id
    session.modified = True
    return redirect(url_for('dashboard'))

@app.route('/delete_chat/<chat_session_id>')
def delete_chat(chat_session_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    db.execute('DELETE FROM history WHERE chat_session_id=? AND user_id=?', (chat_session_id, session['user_id']))
    db.commit()
    db.close()
    if session.get('current_chat_id') == chat_session_id:
        session['chat_history'] = []
        session['current_chat_id'] = None
        session.modified = True
    return redirect(url_for('dashboard'))

@app.route('/delete/<int:id>')
def delete(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    db.execute('DELETE FROM history WHERE id=? AND user_id=?', (id, session['user_id']))
    db.commit()
    db.close()`
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
