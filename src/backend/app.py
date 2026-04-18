import os
import sqlite3

from flask import (Flask, render_template, request, redirect,
                   url_for, session, g, flash, jsonify, send_from_directory)
from database import get_db, init_app

app = Flask(__name__,
            template_folder='../frontend/templates',
            static_folder='../frontend/static')
app.secret_key = 'dev'
app.config['DATABASE'] = os.path.join(app.instance_path, 'learning_platform.db')
init_app(app)


# ═══════════════════════════════════════════════════════════════
#  MIDDLEWARE
# ═══════════════════════════════════════════════════════════════

@app.before_request
def load_logged_in_user():
    g.user    = None
    g.teacher = None
    db = get_db()
    if uid := session.get('user_id'):
        g.user    = db.execute('SELECT * FROM users    WHERE id=?', (uid,)).fetchone()
    if tid := session.get('teacher_id'):
        g.teacher = db.execute('SELECT * FROM teachers WHERE id=?', (tid,)).fetchone()


# ═══════════════════════════════════════════════════════════════
#  STUDENT PAGES
# ═══════════════════════════════════════════════════════════════

@app.route('/')
def index():        return render_template('index.html')

@app.route('/register')
def register_page(): return render_template('register.html')

@app.route('/login')
def login_page():    return render_template('login.html')

@app.route('/catalog')
def catalog_page():  return render_template('catalog.html')

@app.route('/dashboard')
def dashboard():
    if g.user is None: return redirect(url_for('login_page'))
    db = get_db()
    courses = db.execute('''
        SELECT c.* FROM courses c
        JOIN user_courses uc ON c.id=uc.course_id WHERE uc.user_id=?
    ''', (g.user['id'],)).fetchall()
    return render_template('dashboard.html', courses=courses, user=g.user)

@app.route('/course/<int:course_id>')
def course(course_id):
    if g.user is None: return redirect(url_for('login_page'))
    db = get_db()
    if not db.execute('SELECT 1 FROM user_courses WHERE user_id=? AND course_id=?',
                      (g.user['id'], course_id)).fetchone():
        flash('У вас нет доступа к этому курсу')
        return redirect(url_for('dashboard'))
    c = db.execute('SELECT * FROM courses WHERE id=?', (course_id,)).fetchone()
    if not c: flash('Курс не найден'); return redirect(url_for('dashboard'))
    return render_template('course.html', course=c, user=g.user)


# ═══════════════════════════════════════════════════════════════
#  TEACHER PAGES
# ═══════════════════════════════════════════════════════════════

@app.route('/teacher/register')
def teacher_register_page(): return render_template('teacher/register.html')

@app.route('/teacher/login')
def teacher_login_page():    return render_template('teacher/login.html')

@app.route('/teacher/logout')
def teacher_logout():
    session.pop('teacher_id', None)
    return redirect(url_for('teacher_login_page'))

@app.route('/teacher/dashboard')
def teacher_dashboard():
    if g.teacher is None: return redirect(url_for('teacher_login_page'))
    db = get_db()
    courses = db.execute(
        'SELECT * FROM courses WHERE teacher_id=? ORDER BY id DESC', (g.teacher['id'],)
    ).fetchall()
    return render_template('teacher/dashboard.html', teacher=g.teacher, courses=courses)

@app.route('/teacher/course/<int:course_id>')
def teacher_course(course_id):
    if g.teacher is None: return redirect(url_for('teacher_login_page'))
    db = get_db()
    c = db.execute('SELECT * FROM courses WHERE id=? AND teacher_id=?',
                   (course_id, g.teacher['id'])).fetchone()
    if not c: return redirect(url_for('teacher_dashboard'))
    return render_template('teacher/course_manage.html', course=c, teacher=g.teacher)

@app.route('/teacher/builder')
@app.route('/teacher/builder/<int:course_id>')
def teacher_builder(course_id=None):
    if g.teacher is None: return redirect(url_for('teacher_login_page'))
    course = None
    if course_id:
        course = get_db().execute(
            'SELECT * FROM courses WHERE id=? AND teacher_id=?',
            (course_id, g.teacher['id'])
        ).fetchone()
    return render_template('teacher/builder.html', teacher=g.teacher, course=course)

@app.route('/teacher/requests')
def teacher_requests_page():
    if g.teacher is None: return redirect(url_for('teacher_login_page'))
    return render_template('teacher/requests.html', teacher=g.teacher)

@app.route('/api/teacher/all-requests')
def api_teacher_all_requests():
    """All pending requests across all courses of this teacher."""
    err = _require_teacher()
    if err: return err
    db = get_db()
    courses = db.execute('SELECT * FROM courses WHERE teacher_id=? ORDER BY title',
                         (g.teacher['id'],)).fetchall()
    result = []
    for c in courses:
        reqs = db.execute('''SELECT cr.id, cr.status, cr.created_at, u.login, u.first_name, u.last_name
            FROM course_requests cr JOIN users u ON cr.user_id=u.id
            WHERE cr.course_id=? ORDER BY cr.created_at DESC''', (c['id'],)).fetchall()
        pending = sum(1 for r in reqs if r['status'] == 'pending')
        result.append({
            'course_id': c['id'], 'course_title': c['title'],
            'pending': pending,
            'requests': [dict(r) for r in reqs]
        })
    return jsonify([r for r in result if r['requests']])

@app.route('/teacher/catalog')
def teacher_catalog():
    if g.teacher is None: return redirect(url_for('teacher_login_page'))
    return render_template('teacher/catalog_view.html', teacher=g.teacher)


# ═══════════════════════════════════════════════════════════════
#  AUTH API — STUDENTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json; db = get_db()
    try:
        if db.execute('SELECT 1 FROM users WHERE login=?', (data['username'],)).fetchone():
            return jsonify({'error': 'Пользователь с таким логином уже существует'}), 400
        cur = db.execute(
            'INSERT INTO users (login,password,first_name,last_name) VALUES (?,?,?,?)',
            (data['username'], data['password'], data['name'], data['surname'])
        )
        db.commit()
        session['user_id'] = cur.lastrowid
        return jsonify({'success': True})
    except Exception as e: return jsonify({'error': str(e)}), 400

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json; db = get_db()
    user = db.execute('SELECT * FROM users WHERE login=? AND password=?',
                      (data['username'], data['password'])).fetchone()
    if user:
        session['user_id'] = user['id']
        return jsonify({'success': True})
    return jsonify({'error': 'Неверный логин или пароль'}), 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ═══════════════════════════════════════════════════════════════
#  AUTH API — TEACHERS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/teacher/register', methods=['POST'])
def api_teacher_register():
    data = request.json; db = get_db()
    try:
        if db.execute('SELECT 1 FROM teachers WHERE login=?', (data['username'],)).fetchone():
            return jsonify({'error': 'Преподаватель с таким логином уже существует'}), 400
        cur = db.execute(
            'INSERT INTO teachers (login,password,first_name,last_name) VALUES (?,?,?,?)',
            (data['username'], data['password'], data['name'], data['surname'])
        )
        db.commit()
        session['teacher_id'] = cur.lastrowid
        return jsonify({'success': True})
    except Exception as e: return jsonify({'error': str(e)}), 400

@app.route('/api/teacher/login', methods=['POST'])
def api_teacher_login():
    data = request.json; db = get_db()
    t = db.execute('SELECT * FROM teachers WHERE login=? AND password=?',
                   (data['username'], data['password'])).fetchone()
    if t:
        session['teacher_id'] = t['id']
        return jsonify({'success': True})
    return jsonify({'error': 'Неверный логин или пароль'}), 401


# ═══════════════════════════════════════════════════════════════
#  CATALOG API
# ═══════════════════════════════════════════════════════════════

@app.route('/api/catalog/open')
def catalog_open():
    db = get_db(); user_id = g.user['id'] if g.user else None
    courses = db.execute('SELECT * FROM courses WHERE is_open=1 ORDER BY id').fetchall()
    result = []
    for c in courses:
        enrolled = pending = False
        if user_id:
            enrolled = bool(db.execute('SELECT 1 FROM user_courses WHERE user_id=? AND course_id=?',
                                       (user_id, c['id'])).fetchone())
            if not enrolled:
                pending = bool(db.execute(
                    "SELECT 1 FROM course_requests WHERE user_id=? AND course_id=? AND status='pending'",
                    (user_id, c['id'])).fetchone())
        result.append({'id': c['id'], 'title': c['title'], 'is_open': c['is_open'],
                       'description': c['description'] or '', 'enrolled': enrolled, 'pending': pending})
    return jsonify(result)

@app.route('/api/catalog/search', methods=['POST'])
def catalog_search():
    if g.user is None: return jsonify({'error': 'Необходимо войти в аккаунт'}), 401
    title = (request.json.get('title') or '').strip()
    if not title: return jsonify({'error': 'Введите название курса'}), 400
    db = get_db()
    c = db.execute('SELECT * FROM courses WHERE LOWER(title)=LOWER(?) AND is_open=0', (title,)).fetchone()
    if not c: return jsonify({'error': 'Курс с таким названием не найден'}), 404
    if db.execute('SELECT 1 FROM user_courses WHERE user_id=? AND course_id=?',
                  (g.user['id'], c['id'])).fetchone():
        return jsonify({'error': 'Вы уже записаны на этот курс'}), 400
    # Check existing request status
    existing = db.execute(
        "SELECT status FROM course_requests WHERE user_id=? AND course_id=? ORDER BY id DESC LIMIT 1",
        (g.user['id'], c['id'])).fetchone()
    if existing and existing['status'] == 'pending':
        return jsonify({'error': 'Заявка уже отправлена и ожидает рассмотрения'}), 400
    if existing and existing['status'] == 'rejected':
        return jsonify({'rejected': True, 'course_title': c['title'], 'course_id': c['id']}), 200
    db.execute("INSERT INTO course_requests (user_id,course_id,status) VALUES (?,?,'pending')",
               (g.user['id'], c['id']))
    db.commit()
    return jsonify({'success': True, 'course_title': c['title']})

@app.route('/api/catalog/reapply/<int:course_id>', methods=['POST'])
def catalog_reapply(course_id):
    if g.user is None: return jsonify({'error': 'Необходимо войти в аккаунт'}), 401
    db = get_db()
    c = db.execute('SELECT * FROM courses WHERE id=? AND is_open=0', (course_id,)).fetchone()
    if not c: return jsonify({'error': 'Курс не найден'}), 404
    if db.execute('SELECT 1 FROM user_courses WHERE user_id=? AND course_id=?',
                  (g.user['id'], course_id)).fetchone():
        return jsonify({'error': 'Вы уже записаны на этот курс'}), 400
    # Delete old rejected request, insert new pending one
    db.execute("DELETE FROM course_requests WHERE user_id=? AND course_id=?",
               (g.user['id'], course_id))
    db.execute("INSERT INTO course_requests (user_id,course_id,status) VALUES (?,?,'pending')",
               (g.user['id'], course_id))
    db.commit()
    return jsonify({'success': True, 'course_title': c['title']})

@app.route('/api/catalog/enroll/<int:course_id>', methods=['POST'])
def catalog_enroll(course_id):
    if g.user is None: return jsonify({'error': 'Необходимо войти в аккаунт'}), 401
    db = get_db()
    if not db.execute('SELECT 1 FROM courses WHERE id=? AND is_open=1', (course_id,)).fetchone():
        return jsonify({'error': 'Курс не найден или закрытый'}), 404
    db.execute('INSERT OR IGNORE INTO user_courses (user_id,course_id) VALUES (?,?)',
               (g.user['id'], course_id))
    db.commit()
    return jsonify({'success': True})


# ═══════════════════════════════════════════════════════════════
#  TEACHER — COURSES
# ═══════════════════════════════════════════════════════════════

def _require_teacher():
    if g.teacher is None: return jsonify({'error': 'Not authorized'}), 401
    return None

@app.route('/api/teacher/courses', methods=['GET'])
def api_teacher_courses():
    err = _require_teacher()
    if err: return err
    db = get_db()
    courses = db.execute('SELECT * FROM courses WHERE teacher_id=? ORDER BY id DESC',
                         (g.teacher['id'],)).fetchall()
    result = []
    for c in courses:
        student_count = db.execute('SELECT COUNT(*) as n FROM user_courses WHERE course_id=?',
                                   (c['id'],)).fetchone()['n']
        block_count   = db.execute('SELECT COUNT(*) as n FROM course_blocks WHERE course_id=?',
                                   (c['id'],)).fetchone()['n']
        pending_reqs  = db.execute(
            "SELECT COUNT(*) as n FROM course_requests WHERE course_id=? AND status='pending'",
            (c['id'],)).fetchone()['n']
        result.append({'id': c['id'], 'title': c['title'], 'description': c['description'] or '',
                       'is_open': c['is_open'], 'students': student_count, 'blocks': block_count,
                       'pending_requests': pending_reqs})
    return jsonify(result)

@app.route('/api/teacher/courses', methods=['POST'])
def api_teacher_create_course():
    err = _require_teacher()
    if err: return err
    data = request.json; db = get_db()
    try:
        cur = db.execute(
            'INSERT INTO courses (title,description,is_open,teacher_id) VALUES (?,?,?,?)',
            (data['title'], data.get('description',''), 1 if data.get('is_open') else 0, g.teacher['id'])
        )
        db.commit()
        return jsonify({'success': True, 'course_id': cur.lastrowid})
    except Exception as e: return jsonify({'error': str(e)}), 400

@app.route('/api/teacher/courses/<int:course_id>', methods=['PUT'])
def api_teacher_update_course(course_id):
    err = _require_teacher()
    if err: return err
    data = request.json; db = get_db()
    db.execute('UPDATE courses SET title=?,description=?,is_open=? WHERE id=? AND teacher_id=?',
               (data['title'], data.get('description',''), 1 if data.get('is_open') else 0,
                course_id, g.teacher['id']))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/teacher/courses/<int:course_id>', methods=['DELETE'])
def api_teacher_delete_course(course_id):
    err = _require_teacher()
    if err: return err
    db = get_db()
    db.execute('DELETE FROM courses WHERE id=? AND teacher_id=?', (course_id, g.teacher['id']))
    db.commit()
    return jsonify({'success': True})


# ═══════════════════════════════════════════════════════════════
#  TEACHER — BLOCKS (новая структура: курс → блоки → уроки/задания)
# ═══════════════════════════════════════════════════════════════

@app.route('/api/teacher/courses/<int:course_id>/blocks', methods=['GET'])
def api_teacher_blocks(course_id):
    err = _require_teacher()
    if err: return err
    db = get_db()
    if not db.execute('SELECT 1 FROM courses WHERE id=? AND teacher_id=?',
                      (course_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404

    blocks = db.execute(
        'SELECT * FROM course_blocks WHERE course_id=? ORDER BY order_index', (course_id,)
    ).fetchall()

    result = []
    for b in blocks:
        items = db.execute(
            'SELECT * FROM block_items WHERE block_id=? ORDER BY order_index', (b['id'],)
        ).fetchall()
        items_out = []
        for it in items:
            item_d = {
                'id': it['id'], 'type': it['type'], 'title': it['title'],
                'order_index': it['order_index']
            }
            if it['type'] == 'lesson':
                lesson = db.execute('SELECT * FROM lessons WHERE id=?', (it['lesson_id'],)).fetchone()
                if lesson:
                    mats = db.execute('SELECT * FROM lesson_materials WHERE lesson_id=?',
                                      (lesson['id'],)).fetchall()
                    item_d['lesson'] = {
                        'id': lesson['id'], 'title': lesson['title'],
                        'content': lesson['content'], 'home_work': lesson['home_work'],
                        'materials': [{'id': m['id'], 'type': m['type'], 'title': m['title'],
                                       'youtube_id': m['youtube_id'], 'file_path': m['file_path']}
                                      for m in mats]
                    }
            elif it['type'] == 'task':
                task = db.execute('SELECT * FROM tasks WHERE id=?', (it['task_id'],)).fetchone()
                if task:
                    item_d['task'] = {
                        'id': task['id'], 'question': task['question'],
                        'task_type': task['task_type'], 'options': task['options'] or '',
                        'correct_answer': task['correct_answer'] or '',
                        'max_attempts': task['max_attempts'] if 'max_attempts' in task.keys() else 100
                    }
            items_out.append(item_d)

        result.append({
            'id': b['id'], 'title': b['title'], 'order_index': b['order_index'],
            'items': items_out
        })
    return jsonify(result)


@app.route('/api/teacher/courses/<int:course_id>/blocks', methods=['POST'])
def api_teacher_create_block(course_id):
    err = _require_teacher()
    if err: return err
    data = request.json; db = get_db()
    if not db.execute('SELECT 1 FROM courses WHERE id=? AND teacher_id=?',
                      (course_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404
    max_o = db.execute('SELECT COALESCE(MAX(order_index),0) as m FROM course_blocks WHERE course_id=?',
                       (course_id,)).fetchone()['m']
    cur = db.execute('INSERT INTO course_blocks (course_id,title,order_index) VALUES (?,?,?)',
                     (course_id, data.get('title','Новый блок'), max_o + 1))
    db.commit()
    return jsonify({'success': True, 'block_id': cur.lastrowid})


@app.route('/api/teacher/blocks/<int:block_id>', methods=['PUT'])
def api_teacher_update_block(block_id):
    err = _require_teacher()
    if err: return err
    data = request.json; db = get_db()
    # Verify ownership
    if not db.execute('''SELECT 1 FROM course_blocks cb JOIN courses c ON cb.course_id=c.id
                         WHERE cb.id=? AND c.teacher_id=?''', (block_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404
    db.execute('UPDATE course_blocks SET title=? WHERE id=?', (data['title'], block_id))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/teacher/blocks/<int:block_id>', methods=['DELETE'])
def api_teacher_delete_block(block_id):
    err = _require_teacher()
    if err: return err
    db = get_db()
    if not db.execute('''SELECT 1 FROM course_blocks cb JOIN courses c ON cb.course_id=c.id
                         WHERE cb.id=? AND c.teacher_id=?''', (block_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404
    db.execute('DELETE FROM course_blocks WHERE id=?', (block_id,))
    db.commit()
    return jsonify({'success': True})


# ── Block items: lessons ──────────────────────────────────────

@app.route('/api/teacher/blocks/<int:block_id>/items/lesson', methods=['POST'])
def api_teacher_add_lesson(block_id):
    err = _require_teacher()
    if err: return err
    data = request.json; db = get_db()
    if not db.execute('''SELECT 1 FROM course_blocks cb JOIN courses c ON cb.course_id=c.id
                         WHERE cb.id=? AND c.teacher_id=?''', (block_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404

    # Get course_id for lessons table
    block = db.execute('SELECT * FROM course_blocks WHERE id=?', (block_id,)).fetchone()
    max_o = db.execute('SELECT COALESCE(MAX(order_index),0) as m FROM lessons WHERE course_id=?',
                       (block['course_id'],)).fetchone()['m']

    lesson_cur = db.execute(
        'INSERT INTO lessons (title,content,home_work,order_index,course_id) VALUES (?,?,?,?,?)',
        (data.get('title','Новый урок'), data.get('content',''),
         0, max_o + 1, block['course_id'])
    )
    lesson_id = lesson_cur.lastrowid

    for mat in data.get('materials', []):
        db.execute('INSERT INTO lesson_materials (lesson_id,type,title,youtube_id,file_path) VALUES (?,?,?,?,?)',
                   (lesson_id, mat['type'], mat['title'],
                    mat.get('youtube_id',''), mat.get('file_path','')))

    max_item = db.execute('SELECT COALESCE(MAX(order_index),0) as m FROM block_items WHERE block_id=?',
                          (block_id,)).fetchone()['m']
    item_cur = db.execute(
        "INSERT INTO block_items (block_id,type,lesson_id,task_id,title,order_index) VALUES (?,?,?,NULL,?,?)",
        (block_id, 'lesson', lesson_id, data.get('title','Новый урок'), max_item + 1)
    )
    db.commit()
    return jsonify({'success': True, 'lesson_id': lesson_id, 'item_id': item_cur.lastrowid})


@app.route('/api/teacher/items/lesson/<int:lesson_id>', methods=['PUT'])
def api_teacher_update_lesson(lesson_id):
    err = _require_teacher()
    if err: return err
    data = request.json; db = get_db()
    if not db.execute('''SELECT 1 FROM lessons l JOIN courses c ON l.course_id=c.id
                         WHERE l.id=? AND c.teacher_id=?''', (lesson_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404
    db.execute('UPDATE lessons SET title=?,content=?,home_work=0 WHERE id=?',
               (data['title'], data.get('content',''), lesson_id))
    db.execute('DELETE FROM lesson_materials WHERE lesson_id=?', (lesson_id,))
    for mat in data.get('materials', []):
        db.execute('INSERT INTO lesson_materials (lesson_id,type,title,youtube_id,file_path) VALUES (?,?,?,?,?)',
                   (lesson_id, mat['type'], mat['title'],
                    mat.get('youtube_id',''), mat.get('file_path','')))
    db.execute('UPDATE block_items SET title=? WHERE lesson_id=?', (data['title'], lesson_id))
    db.commit()
    return jsonify({'success': True})


# ── Block items: tasks ────────────────────────────────────────

@app.route('/api/teacher/blocks/<int:block_id>/items/task', methods=['POST'])
def api_teacher_add_task(block_id):
    err = _require_teacher()
    if err: return err
    data = request.json; db = get_db()
    if not db.execute('''SELECT 1 FROM course_blocks cb JOIN courses c ON cb.course_id=c.id
                         WHERE cb.id=? AND c.teacher_id=?''', (block_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404

    block = db.execute('SELECT * FROM course_blocks WHERE id=?', (block_id,)).fetchone()
    task_cur = db.execute(
        'INSERT INTO tasks (course_id,question,task_type,options,correct_answer,max_attempts) VALUES (?,?,?,?,?,?)',
        (block['course_id'], data.get('question','Вопрос задания'),
         data.get('task_type','text'), data.get('options',''), data.get('correct_answer',''),
         data.get('max_attempts', 100))
    )
    task_id = task_cur.lastrowid

    max_item = db.execute('SELECT COALESCE(MAX(order_index),0) as m FROM block_items WHERE block_id=?',
                          (block_id,)).fetchone()['m']
    item_cur = db.execute(
        "INSERT INTO block_items (block_id,type,lesson_id,task_id,title,order_index) VALUES (?,?,NULL,?,?,?)",
        (block_id, 'task', task_id, data.get('question','Новое задание'), max_item + 1)
    )
    db.commit()
    return jsonify({'success': True, 'task_id': task_id, 'item_id': item_cur.lastrowid})


@app.route('/api/teacher/items/task/<int:task_id>', methods=['PUT'])
def api_teacher_update_task(task_id):
    err = _require_teacher()
    if err: return err
    data = request.json; db = get_db()
    if not db.execute('''SELECT 1 FROM tasks t JOIN courses c ON t.course_id=c.id
                         WHERE t.id=? AND c.teacher_id=?''', (task_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404
    db.execute('UPDATE tasks SET question=?,task_type=?,options=?,correct_answer=?,max_attempts=? WHERE id=?',
               (data['question'], data.get('task_type','text'),
                data.get('options',''), data.get('correct_answer',''),
                data.get('max_attempts', 100), task_id))
    db.execute('UPDATE block_items SET title=? WHERE task_id=?', (data['question'], task_id))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/teacher/items/<int:item_id>', methods=['DELETE'])
def api_teacher_delete_item(item_id):
    err = _require_teacher()
    if err: return err
    db = get_db()
    item = db.execute('SELECT * FROM block_items WHERE id=?', (item_id,)).fetchone()
    if not item: return jsonify({'error': 'Not found'}), 404
    # Verify ownership
    if not db.execute('''SELECT 1 FROM course_blocks cb JOIN courses c ON cb.course_id=c.id
                         WHERE cb.id=? AND c.teacher_id=?''',
                      (item['block_id'], g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404
    db.execute('DELETE FROM block_items WHERE id=?', (item_id,))
    if item['type'] == 'lesson' and item['lesson_id']:
        db.execute('DELETE FROM lessons WHERE id=?', (item['lesson_id'],))
    elif item['type'] == 'task' and item['task_id']:
        db.execute('DELETE FROM tasks WHERE id=?', (item['task_id'],))
    db.commit()
    return jsonify({'success': True})


# ── Old lessons API (still used for student course view) ──────

@app.route('/api/teacher/courses/<int:course_id>/lessons', methods=['GET'])
def api_teacher_lessons(course_id):
    """Compatibility: returns flat list of lessons for course manage page homework tab."""
    err = _require_teacher()
    if err: return err
    db = get_db()
    if not db.execute('SELECT 1 FROM courses WHERE id=? AND teacher_id=?',
                      (course_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404
    lessons = db.execute('SELECT * FROM lessons WHERE course_id=? ORDER BY order_index',
                         (course_id,)).fetchall()
    result = []
    for l in lessons:
        mats = db.execute('SELECT * FROM lesson_materials WHERE lesson_id=?', (l['id'],)).fetchall()
        result.append({'id': l['id'], 'title': l['title'], 'content': l['content'],
                       'order_index': l['order_index'], 'home_work': l['home_work'],
                       'materials': [{'id': m['id'], 'type': m['type'], 'title': m['title'],
                                      'youtube_id': m['youtube_id'], 'file_path': m['file_path']}
                                     for m in mats]})
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════
#  TEACHER — HOMEWORK, STUDENTS, REQUESTS (unchanged)
# ═══════════════════════════════════════════════════════════════

@app.route('/api/teacher/courses/<int:course_id>/homework')
def api_teacher_homework(course_id):
    err = _require_teacher()
    if err: return err
    db = get_db()
    if not db.execute('SELECT 1 FROM courses WHERE id=? AND teacher_id=?',
                      (course_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404

    # Homework from lessons (legacy home_work flag - kept for compatibility)
    lesson_rows = db.execute('''
        SELECT ha.id, ha.answer_text, ha.submitted_at, ha.status,
               u.login, u.first_name, u.last_name,
               l.title as lesson_title, l.id as lesson_id,
               c.comment as teacher_comment, ha.comment_id,
               'lesson_hw' as source, NULL as task_id,
               cb.title as block_title
        FROM homework_answers ha
        JOIN users   u ON ha.user_id=u.id
        JOIN lessons l ON ha.lesson_id=l.id
        LEFT JOIN comments c ON ha.comment_id=c.id
        LEFT JOIN block_items bi ON bi.lesson_id=l.id
        LEFT JOIN course_blocks cb ON bi.block_id=cb.id
        WHERE l.course_id=? ORDER BY ha.submitted_at DESC
    ''', (course_id,)).fetchall()

    # Answers to text-type tasks (require teacher review)
    task_rows = db.execute('''
        SELECT ta.id, ta.answer_text, ta.answered_at as submitted_at,
               CASE WHEN ta.is_correct IS NULL THEN 'submitted'
                    WHEN ta.is_correct = 1 THEN 'checked'
                    ELSE 'rejected' END as status,
               u.login, u.first_name, u.last_name,
               t.question as lesson_title, NULL as lesson_id,
               cmt.comment as teacher_comment, ta.comment_id,
               'task' as source, ta.task_id,
               cb.title as block_title
        FROM task_answers ta
        JOIN users u ON ta.user_id=u.id
        JOIN tasks t ON ta.task_id=t.id
        LEFT JOIN comments cmt ON ta.comment_id=cmt.id
        LEFT JOIN block_items bi ON bi.task_id=t.id
        LEFT JOIN course_blocks cb ON bi.block_id=cb.id
        WHERE t.course_id=? AND t.task_type='text'
        ORDER BY ta.answered_at DESC
    ''', (course_id,)).fetchall()

    result = [dict(r) for r in lesson_rows] + [dict(r) for r in task_rows]
    result.sort(key=lambda x: x['submitted_at'] or '', reverse=True)
    return jsonify(result)

@app.route('/api/teacher/homework/<int:answer_id>/review', methods=['POST'])
def api_teacher_review(answer_id):
    err = _require_teacher()
    if err: return err
    data = request.json; db = get_db()
    source = data.get('source', 'lesson_hw')
    comment_text = data.get('comment', '').strip()

    if source == 'task':
        row = db.execute('''SELECT ta.* FROM task_answers ta
            JOIN tasks t ON ta.task_id=t.id JOIN courses c ON t.course_id=c.id
            WHERE ta.id=? AND c.teacher_id=?''', (answer_id, g.teacher['id'])).fetchone()
        if not row: return jsonify({'error': 'Not found'}), 404
        status = data.get('status', 'checked')
        is_correct = 1 if status == 'checked' else 0
        if comment_text:
            existing_cid = row['comment_id'] if 'comment_id' in row.keys() else None
            if existing_cid:
                db.execute('UPDATE comments SET comment=? WHERE id=?', (comment_text, existing_cid))
                comment_id = existing_cid
            else:
                cur = db.execute('INSERT INTO comments (comment) VALUES (?)', (comment_text,))
                comment_id = cur.lastrowid
            try:
                db.execute('UPDATE task_answers SET is_correct=?,comment_id=? WHERE id=?',
                           (is_correct, comment_id, answer_id))
            except Exception:
                db.execute('UPDATE task_answers SET is_correct=? WHERE id=?', (is_correct, answer_id))
        else:
            db.execute('UPDATE task_answers SET is_correct=? WHERE id=?', (is_correct, answer_id))
        # Save to history
        if comment_text:
            db.execute('INSERT INTO answer_comments (source,answer_id,author,comment) VALUES (?,?,?,?)',
                       ('task', answer_id, 'teacher', comment_text))
    else:
        row = db.execute('''SELECT ha.* FROM homework_answers ha
            JOIN lessons l ON ha.lesson_id=l.id JOIN courses c ON l.course_id=c.id
            WHERE ha.id=? AND c.teacher_id=?''', (answer_id, g.teacher['id'])).fetchone()
        if not row: return jsonify({'error': 'Not found'}), 404
        if row['comment_id']:
            db.execute('UPDATE comments SET comment=? WHERE id=?', (comment_text, row['comment_id']))
            comment_id = row['comment_id']
        else:
            cur = db.execute('INSERT INTO comments (comment) VALUES (?)', (comment_text,))
            comment_id = cur.lastrowid
        db.execute('UPDATE homework_answers SET status=?,comment_id=? WHERE id=?',
                   (data.get('status', 'checked'), comment_id, answer_id))
        # Save to history
        if comment_text:
            db.execute('INSERT INTO answer_comments (source,answer_id,author,comment) VALUES (?,?,?,?)',
                       ('lesson_hw', answer_id, 'teacher', comment_text))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/teacher/homework/<int:answer_id>/history')
def api_answer_history(answer_id):
    """Returns comment history for a given answer."""
    err = _require_teacher()
    if err: return err
    db = get_db()
    rows = db.execute('''SELECT author, comment, created_at FROM answer_comments
        WHERE answer_id=? ORDER BY created_at ASC''', (answer_id,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/teacher/students')
def api_teacher_all_students():
    """Returns all students enrolled in any course by this teacher, with progress per course."""
    err = _require_teacher()
    if err: return err
    db = get_db()
    rows = db.execute('''
        SELECT DISTINCT u.id, u.login, u.first_name, u.last_name,
               c.id as course_id, c.title as course_title
        FROM users u
        JOIN user_courses uc ON u.id = uc.user_id
        JOIN courses c ON uc.course_id = c.id
        WHERE c.teacher_id = ?
        ORDER BY u.last_name, u.first_name, c.title
    ''', (g.teacher['id'],)).fetchall()

    # Precompute totals per course (lessons + tasks)
    course_totals = {}
    for r in rows:
        cid = r['course_id']
        if cid not in course_totals:
            tl = db.execute('SELECT COUNT(*) as n FROM lessons WHERE course_id=?', (cid,)).fetchone()['n']
            tt = db.execute('''SELECT COUNT(*) as n FROM tasks t
                               JOIN block_items bi ON bi.task_id=t.id
                               WHERE t.course_id=?''', (cid,)).fetchone()['n']
            course_totals[cid] = tl + tt

    # Group by student, compute progress per course
    students = {}
    for r in rows:
        sid = r['id']
        cid = r['course_id']
        if sid not in students:
            students[sid] = {
                'id': sid, 'login': r['login'],
                'first_name': r['first_name'], 'last_name': r['last_name'],
                'courses': []
            }
        total = course_totals[cid]
        comp_lessons = db.execute('''
            SELECT COUNT(*) as n FROM user_progress up
            JOIN lessons l ON up.lesson_id=l.id
            WHERE up.user_id=? AND up.completed=1 AND l.course_id=?''',
            (sid, cid)).fetchone()['n']
        comp_tasks = db.execute('''
            SELECT COUNT(*) as n FROM task_answers ta
            JOIN tasks t ON ta.task_id=t.id
            WHERE ta.user_id=? AND t.course_id=? AND ta.is_correct=1''',
            (sid, cid)).fetchone()['n']
        completed = comp_lessons + comp_tasks
        progress = int(completed / total * 100) if total else 0
        students[sid]['courses'].append({
            'id': cid, 'title': r['course_title'],
            'progress': progress, 'completed': completed, 'total': total
        })
    return jsonify(list(students.values()))


@app.route('/teacher/students')
def teacher_students_page():
    if g.teacher is None: return redirect(url_for('teacher_login_page'))
    return render_template('teacher/students.html', teacher=g.teacher)



@app.route('/api/teacher/courses/<int:course_id>/students')
def api_teacher_students(course_id):
    err = _require_teacher()
    if err: return err
    db = get_db()
    if not db.execute('SELECT 1 FROM courses WHERE id=? AND teacher_id=?',
                      (course_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404
    total_lessons = db.execute('SELECT COUNT(*) as n FROM lessons WHERE course_id=?',
                               (course_id,)).fetchone()['n']
    total_tasks = db.execute('''SELECT COUNT(*) as n FROM tasks t
        JOIN block_items bi ON bi.task_id=t.id WHERE t.course_id=?''',
        (course_id,)).fetchone()['n']
    total = total_lessons + total_tasks
    students = db.execute('''SELECT u.id, u.login, u.first_name, u.last_name
        FROM users u JOIN user_courses uc ON u.id=uc.user_id WHERE uc.course_id=?''',
        (course_id,)).fetchall()
    result = []
    for s in students:
        done_lessons = db.execute('''SELECT COUNT(*) as n FROM user_progress up
            JOIN lessons l ON up.lesson_id=l.id
            WHERE up.user_id=? AND up.completed=1 AND l.course_id=?''',
            (s['id'], course_id)).fetchone()['n']
        done_tasks = db.execute('''SELECT COUNT(*) as n FROM task_answers ta
            JOIN tasks t ON ta.task_id=t.id
            WHERE ta.user_id=? AND t.course_id=? AND ta.is_correct=1''',
            (s['id'], course_id)).fetchone()['n']
        done = done_lessons + done_tasks
        progress = int(done / total * 100) if total else 0
        result.append({'id': s['id'], 'login': s['login'],
                       'first_name': s['first_name'], 'last_name': s['last_name'],
                       'completed': done, 'total': total, 'progress': progress})
    return jsonify(result)

@app.route('/api/teacher/courses/<int:course_id>/students/<int:user_id>', methods=['DELETE'])
def api_teacher_unenroll(course_id, user_id):
    err = _require_teacher()
    if err: return err
    db = get_db()
    if not db.execute('SELECT 1 FROM courses WHERE id=? AND teacher_id=?',
                      (course_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404
    db.execute('DELETE FROM user_courses WHERE user_id=? AND course_id=?', (user_id, course_id))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/teacher/courses/<int:course_id>/requests')
def api_teacher_requests(course_id):
    err = _require_teacher()
    if err: return err
    db = get_db()
    if not db.execute('SELECT 1 FROM courses WHERE id=? AND teacher_id=?',
                      (course_id, g.teacher['id'])).fetchone():
        return jsonify({'error': 'Not found'}), 404
    rows = db.execute('''SELECT cr.id, cr.status, cr.created_at, u.login, u.first_name, u.last_name
        FROM course_requests cr JOIN users u ON cr.user_id=u.id
        WHERE cr.course_id=? ORDER BY cr.created_at DESC''', (course_id,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/teacher/requests/<int:req_id>/approve', methods=['POST'])
def api_teacher_approve(req_id):
    err = _require_teacher()
    if err: return err
    db = get_db()
    row = db.execute('''SELECT cr.* FROM course_requests cr JOIN courses c ON cr.course_id=c.id
        WHERE cr.id=? AND c.teacher_id=?''', (req_id, g.teacher['id'])).fetchone()
    if not row: return jsonify({'error': 'Not found'}), 404
    db.execute('UPDATE course_requests SET status=? WHERE id=?', ('approved', req_id))
    db.execute('INSERT OR IGNORE INTO user_courses (user_id,course_id) VALUES (?,?)',
               (row['user_id'], row['course_id']))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/teacher/requests/<int:req_id>/reject', methods=['POST'])
def api_teacher_reject(req_id):
    err = _require_teacher()
    if err: return err
    db = get_db()
    db.execute('''UPDATE course_requests SET status='rejected' WHERE id=? AND course_id IN
                  (SELECT id FROM courses WHERE teacher_id=?)''', (req_id, g.teacher['id']))
    db.commit()
    return jsonify({'success': True})


# ═══════════════════════════════════════════════════════════════
#  STUDENT — LESSONS & PROGRESS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/courses/<int:course_id>/sections')
def get_course_sections(course_id):
    """Returns blocks with nested items for student course view."""
    if g.user is None: return jsonify({'error': 'Not authorized'}), 401
    db = get_db()
    if not db.execute('SELECT 1 FROM courses WHERE id=?', (course_id,)).fetchone():
        return jsonify({'error': 'Course not found'}), 404

    blocks = db.execute('SELECT * FROM course_blocks WHERE course_id=? ORDER BY order_index',
                        (course_id,)).fetchall()
    result = []
    for b in blocks:
        items = db.execute('SELECT * FROM block_items WHERE block_id=? ORDER BY order_index',
                           (b['id'],)).fetchall()
        items_out = []
        for it in items:
            d = {'id': it['id'], 'type': it['type'], 'title': it['title']}
            if it['type'] == 'lesson' and it['lesson_id']:
                done = db.execute('SELECT 1 FROM user_progress WHERE user_id=? AND lesson_id=?',
                                  (g.user['id'], it['lesson_id'])).fetchone()
                d['lesson_id']    = it['lesson_id']
                d['is_completed'] = done is not None
            elif it['type'] == 'task' and it['task_id']:
                ans = db.execute(
                    '''SELECT ta.is_correct, t.task_type, t.max_attempts,
                              (SELECT COUNT(*) FROM task_attempts att
                               WHERE att.user_id=? AND att.task_id=ta.task_id) as att_count
                       FROM task_answers ta
                       JOIN tasks t ON ta.task_id=t.id
                       WHERE ta.user_id=? AND ta.task_id=?''',
                    (g.user['id'], g.user['id'], it['task_id'])
                ).fetchone()
                max_att = db.execute('SELECT max_attempts FROM tasks WHERE id=?',
                                     (it['task_id'],)).fetchone()
                d['task_id'] = it['task_id']
                d['max_attempts'] = (max_att['max_attempts'] if max_att else 100)
                if ans is None:
                    d['is_completed'] = False
                    d['attempts_used'] = 0
                else:
                    d['attempts_used'] = ans['att_count']
                    # Completed only if teacher/auto accepted (is_correct == 1)
                    d['is_completed'] = (ans['is_correct'] == 1)
            items_out.append(d)
        result.append({'id': b['id'], 'title': b['title'], 'items': items_out})

    # Fallback: if no blocks but has lessons (legacy), wrap in one block
    if not result:
        lessons = db.execute('SELECT * FROM lessons WHERE course_id=? ORDER BY order_index',
                             (course_id,)).fetchall()
        if lessons:
            items_out = []
            for l in lessons:
                done = db.execute('SELECT 1 FROM user_progress WHERE user_id=? AND lesson_id=?',
                                  (g.user['id'], l['id'])).fetchone()
                items_out.append({'id': l['id'], 'type': 'lesson', 'title': l['title'],
                                  'lesson_id': l['id'], 'is_completed': done is not None})
            result = [{'id': 0, 'title': 'Уроки', 'items': items_out}]
    return jsonify(result)


@app.route('/api/lessons/<int:lesson_id>')
def get_lesson(lesson_id):
    if g.user is None: return jsonify({'error': 'Not authorized'}), 401
    db = get_db()
    lesson = db.execute('SELECT * FROM lessons WHERE id=?', (lesson_id,)).fetchone()
    if not lesson: return jsonify({'error': 'Lesson not found'}), 404
    # BUG4 FIX: automatically mark lesson as completed when student opens it
    db.execute('INSERT OR REPLACE INTO user_progress (user_id,lesson_id,completed) VALUES (?,?,1)',
               (g.user['id'], lesson_id))
    db.commit()
    materials = db.execute('SELECT * FROM lesson_materials WHERE lesson_id=?', (lesson_id,)).fetchall()
    return jsonify({
        'id': lesson['id'], 'title': lesson['title'], 'content': lesson['content'],
        'materials': [{'id': m['id'], 'type': m['type'], 'title': m['title'],
                       'youtube_id': m['youtube_id'], 'file_path': m['file_path']} for m in materials],
    })


@app.route('/api/tasks/<int:task_id>')
def get_task(task_id):
    if g.user is None: return jsonify({'error': 'Not authorized'}), 401
    db = get_db()
    task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not task: return jsonify({'error': 'Task not found'}), 404
    answer = db.execute('''
        SELECT ta.*, cmt.comment as teacher_comment
        FROM task_answers ta
        LEFT JOIN comments cmt ON ta.comment_id=cmt.id
        WHERE ta.user_id=? AND ta.task_id=?
    ''', (g.user['id'], task_id)).fetchone()
    # Count total attempts submitted (for history-based tasks we track in homework_answers for text)
    attempts_used = db.execute(
        'SELECT COUNT(*) as n FROM task_attempts WHERE user_id=? AND task_id=?',
        (g.user['id'], task_id)
    ).fetchone()['n']
    max_attempts = task['max_attempts'] if 'max_attempts' in task.keys() else 100
    answer_data = None
    if answer:
        answer_data = {
            'text': answer['answer_text'],
            'is_correct': answer['is_correct'],
            'teacher_comment': answer['teacher_comment'] or ''
        }
    return jsonify({
        'id': task['id'], 'question': task['question'], 'task_type': task['task_type'],
        'options': task['options'] or '',
        'max_attempts': max_attempts,
        'attempts_used': attempts_used,
        'answer': answer_data
    })


@app.route('/api/submissions', methods=['POST'])
def create_submission():
    if g.user is None: return jsonify({'error': 'Not authorized'}), 401
    data = request.json; db = get_db()
    try:
        db.execute('INSERT INTO homework_answers (lesson_id,user_id,answer_text,status) VALUES (?,?,?,?)',
                   (data['task_id'], g.user['id'], data['answer'], 'submitted'))
        db.execute('INSERT OR REPLACE INTO user_progress (user_id,lesson_id,completed) VALUES (?,?,1)',
                   (g.user['id'], data['task_id']))
        db.commit()
        return jsonify({'success': True})
    except Exception as e: return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<int:task_id>/answer', methods=['POST'])
def submit_task_answer(task_id):
    if g.user is None: return jsonify({'error': 'Not authorized'}), 401
    data = request.json; db = get_db()
    task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not task: return jsonify({'error': 'Task not found'}), 404

    max_attempts = task['max_attempts'] if 'max_attempts' in task.keys() else 100
    attempts_used = db.execute(
        'SELECT COUNT(*) as n FROM task_attempts WHERE user_id=? AND task_id=?',
        (g.user['id'], task_id)
    ).fetchone()['n']

    # Check if already correctly answered or limit reached
    current = db.execute(
        'SELECT is_correct FROM task_answers WHERE user_id=? AND task_id=?',
        (g.user['id'], task_id)
    ).fetchone()
    if current and current['is_correct'] == 1:
        return jsonify({'error': 'Задание уже выполнено верно'}), 400
    if attempts_used >= max_attempts:
        return jsonify({'error': f'Исчерпан лимит попыток ({max_attempts})'}), 400

    answer_text = data.get('answer', '').strip()
    if not answer_text:
        return jsonify({'error': 'Введите ответ'}), 400

    is_correct = None
    if task['task_type'] in ('choice', 'short') and task['correct_answer']:
        is_correct = 1 if answer_text.lower() == task['correct_answer'].strip().lower() else 0
    elif task['task_type'] == 'match' and task['correct_answer']:
        import json as _json
        try:
            correct = _json.loads(task['correct_answer'])
            submitted = _json.loads(answer_text)
            is_correct = 1 if submitted == correct else 0
        except Exception:
            is_correct = 0
    # text tasks: is_correct stays None until teacher reviews

    # Record this attempt in history
    db.execute(
        'INSERT INTO task_attempts (user_id,task_id,answer_text,is_correct) VALUES (?,?,?,?)',
        (g.user['id'], task_id, answer_text, is_correct)
    )
    # Update (or insert) the current best answer
    db.execute('''INSERT INTO task_answers (user_id,task_id,answer_text,is_correct)
                  VALUES (?,?,?,?) ON CONFLICT(user_id,task_id) DO UPDATE SET
                  answer_text=excluded.answer_text, is_correct=excluded.is_correct''',
               (g.user['id'], task_id, answer_text, is_correct))
    db.commit()

    new_attempts = attempts_used + 1
    remaining = max_attempts - new_attempts
    return jsonify({'success': True, 'is_correct': is_correct,
                    'attempts_used': new_attempts, 'attempts_remaining': remaining})


@app.route('/api/user/progress')
def get_user_progress():
    if g.user is None: return jsonify({'error': 'Not authorized'}), 401
    db = get_db(); course_id = request.args.get('course_id', type=int)
    if course_id:
        total_lessons = db.execute(
            'SELECT COUNT(*) as n FROM lessons WHERE course_id=?', (course_id,)
        ).fetchone()['n']
        total_tasks = db.execute('''
            SELECT COUNT(*) as n FROM tasks t
            JOIN block_items bi ON bi.task_id=t.id
            WHERE t.course_id=?''', (course_id,)
        ).fetchone()['n']
        total = total_lessons + total_tasks

        completed_lessons = db.execute('''
            SELECT COUNT(*) as n FROM user_progress up
            JOIN lessons l ON up.lesson_id=l.id
            WHERE up.user_id=? AND up.completed=1 AND l.course_id=?''',
            (g.user['id'], course_id)
        ).fetchone()['n']
        # Only is_correct=1 counts as completed (wrong answers and pending text tasks don't count)
        completed_tasks = db.execute('''
            SELECT COUNT(*) as n FROM task_answers ta
            JOIN tasks t ON ta.task_id=t.id
            WHERE ta.user_id=? AND t.course_id=? AND ta.is_correct=1''',
            (g.user['id'], course_id)
        ).fetchone()['n']
        completed = completed_lessons + completed_tasks
    else:
        total_lessons = db.execute('SELECT COUNT(*) as n FROM lessons').fetchone()['n']
        total_tasks   = db.execute('SELECT COUNT(*) as n FROM tasks').fetchone()['n']
        total         = total_lessons + total_tasks
        completed_lessons = db.execute(
            'SELECT COUNT(*) as n FROM user_progress WHERE user_id=? AND completed=1',
            (g.user['id'],)
        ).fetchone()['n']
        completed_tasks = db.execute('''
            SELECT COUNT(*) as n FROM task_answers ta
            JOIN tasks t ON ta.task_id=t.id
            WHERE ta.user_id=? AND ta.is_correct=1''',
            (g.user['id'],)
        ).fetchone()['n']
        completed = completed_lessons + completed_tasks
    progress = int(completed / total * 100) if total else 0
    return jsonify({'total_lessons': total, 'completed_lessons': completed, 'progress': progress})


@app.route('/materials/<path:filename>')
def serve_materials(filename):
    return send_from_directory('materials', filename)


# ═══════════════════════════════════════════════════════════════
#  DB INIT
# ═══════════════════════════════════════════════════════════════

def check_and_create_tables(db):
    tables = {
        'teachers': '''CREATE TABLE teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login VARCHAR(25) NOT NULL UNIQUE, password VARCHAR(25) NOT NULL,
            last_name VARCHAR(50) NOT NULL, first_name VARCHAR(50) NOT NULL)''',
        'users': '''CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login VARCHAR(25) NOT NULL UNIQUE, password VARCHAR(25) NOT NULL,
            last_name VARCHAR(50) NOT NULL, first_name VARCHAR(50) NOT NULL)''',
        'courses': '''CREATE TABLE courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title VARCHAR(100) NOT NULL, description TEXT DEFAULT '',
            is_open INTEGER NOT NULL DEFAULT 1, teacher_id INTEGER)''',
        'course_blocks': '''CREATE TABLE course_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL, title TEXT NOT NULL,
            order_index INTEGER NOT NULL DEFAULT 1)''',
        'block_items': '''CREATE TABLE block_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ("lesson","task")),
            lesson_id INTEGER, task_id INTEGER,
            title TEXT NOT NULL DEFAULT "",
            order_index INTEGER NOT NULL DEFAULT 1)''',
        'lessons': '''CREATE TABLE lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, content TEXT NOT NULL DEFAULT "",
            home_work INTEGER NOT NULL DEFAULT 0,
            order_index INTEGER NOT NULL, course_id INTEGER NOT NULL)''',
        'tasks': '''CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            task_type TEXT NOT NULL DEFAULT "text",
            options TEXT DEFAULT "",
            correct_answer TEXT DEFAULT "")''',
        'task_answers': '''CREATE TABLE task_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, task_id INTEGER NOT NULL,
            answer_text TEXT, is_correct INTEGER,
            answered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id))''',
        'task_attempts': '''CREATE TABLE task_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, task_id INTEGER NOT NULL,
            answer_text TEXT, is_correct INTEGER,
            attempted_at DATETIME DEFAULT CURRENT_TIMESTAMP)''',
        'user_progress': '''CREATE TABLE user_progress (
            user_id INTEGER NOT NULL, lesson_id INTEGER NOT NULL,
            completed BOOLEAN NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, lesson_id))''',
        'homework_answers': '''CREATE TABLE homework_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            answer_text TEXT, submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT "pending", comment_id INTEGER)''',
        'comments':  'CREATE TABLE comments (id INTEGER PRIMARY KEY AUTOINCREMENT, comment TEXT NOT NULL)',
        'answer_comments': '''CREATE TABLE answer_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            answer_id INTEGER NOT NULL,
            author TEXT NOT NULL DEFAULT "teacher",
            comment TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''',
        'lesson_materials': '''CREATE TABLE lesson_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL, type TEXT NOT NULL,
            title TEXT NOT NULL, youtube_id TEXT, file_path TEXT)''',
        'user_courses': '''CREATE TABLE user_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
            UNIQUE(user_id, course_id))''',
        'course_requests': '''CREATE TABLE course_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT "pending",
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, course_id))'''
    }
    for tbl, sql in tables.items():
        try:
            db.execute(f'SELECT 1 FROM {tbl} LIMIT 1')
        except sqlite3.OperationalError:
            db.execute(sql)
            print(f'Создана таблица {tbl}')

    migrations = [
        ('courses',      'is_open',      "ALTER TABLE courses ADD COLUMN is_open INTEGER NOT NULL DEFAULT 1"),
        ('courses',      'description',  "ALTER TABLE courses ADD COLUMN description TEXT DEFAULT ''"),
        ('courses',      'teacher_id',   "ALTER TABLE courses ADD COLUMN teacher_id INTEGER"),
        ('task_answers', 'comment_id',   "ALTER TABLE task_answers ADD COLUMN comment_id INTEGER"),
        ('tasks',        'max_attempts', "ALTER TABLE tasks ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 100"),
    ]
    for tbl, col, sql in migrations:
        try:
            db.execute(f'SELECT {col} FROM {tbl} LIMIT 1')
        except sqlite3.OperationalError:
            db.execute(sql)
            print(f'Миграция: добавлена колонка {tbl}.{col}')


def seed_default_data(db):
    """Insert default demo data if it doesn't already exist."""

    # ── Teacher t1 ──────────────────────────────────────────────
    t1 = db.execute("SELECT id FROM teachers WHERE login='t1'").fetchone()
    if not t1:
        t1_id = db.execute(
            "INSERT INTO teachers (login,password,first_name,last_name) VALUES ('t1','1','t1','1')"
        ).lastrowid
        print('Создан преподаватель t1')
    else:
        t1_id = t1['id']

    # ── Students ─────────────────────────────────────────────────
    s1 = db.execute("SELECT id FROM users WHERE login='st1'").fetchone()
    if not s1:
        s1_id = db.execute(
            "INSERT INTO users (login,password,first_name,last_name) VALUES ('st1','1','st1','1')"
        ).lastrowid
        print('Создан студент st1')
    else:
        s1_id = s1['id']

    s2 = db.execute("SELECT id FROM users WHERE login='st2'").fetchone()
    if not s2:
        s2_id = db.execute(
            "INSERT INTO users (login,password,first_name,last_name) VALUES ('st2','2','st2','2')"
        ).lastrowid
        print('Создан студент st2')
    else:
        s2_id = s2['id']

    # ── Helper: create a course with one block + lesson + 3 tasks ──
    def make_course(title, description, is_open):
        existing = db.execute("SELECT id FROM courses WHERE title=? AND teacher_id=?",
                              (title, t1_id)).fetchone()
        if existing:
            return existing['id']

        course_id = db.execute(
            "INSERT INTO courses (title,description,is_open,teacher_id) VALUES (?,?,?,?)",
            (title, description, 1 if is_open else 0, t1_id)
        ).lastrowid

        # Block 1
        block_id = db.execute(
            "INSERT INTO course_blocks (course_id,title,order_index) VALUES (?,?,1)",
            (course_id, 'Блок 1')
        ).lastrowid

        # 1. Урок 1
        lesson_id = db.execute(
            "INSERT INTO lessons (title,content,home_work,order_index,course_id) VALUES (?,?,0,1,?)",
            ('Урок 1', '1', course_id)
        ).lastrowid
        db.execute(
            "INSERT INTO block_items (block_id,type,lesson_id,task_id,title,order_index) "
            "VALUES (?,?,?,NULL,?,1)",
            (block_id, 'lesson', lesson_id, 'Урок 1')
        )

        # 2. Задание: развёрнутый ответ
        task1_id = db.execute(
            "INSERT INTO tasks (course_id,question,task_type,options,correct_answer,max_attempts) "
            "VALUES (?,?,?,?,?,100)",
            (course_id, '1', 'text', '', '')
        ).lastrowid
        db.execute(
            "INSERT INTO block_items (block_id,type,lesson_id,task_id,title,order_index) "
            "VALUES (?,?,NULL,?,?,2)",
            (block_id, 'task', task1_id, '1')
        )

        # 3. Задание: краткий ответ
        task2_id = db.execute(
            "INSERT INTO tasks (course_id,question,task_type,options,correct_answer,max_attempts) "
            "VALUES (?,?,?,?,?,100)",
            (course_id, '123', 'short', '', '123')
        ).lastrowid
        db.execute(
            "INSERT INTO block_items (block_id,type,lesson_id,task_id,title,order_index) "
            "VALUES (?,?,NULL,?,?,3)",
            (block_id, 'task', task2_id, '123')
        )

        # 4. Задание: тест (выбор)
        task3_id = db.execute(
            "INSERT INTO tasks (course_id,question,task_type,options,correct_answer,max_attempts) "
            "VALUES (?,?,?,?,?,100)",
            (course_id, '1', 'choice', '1\n2\n3\n4', '2')
        ).lastrowid
        db.execute(
            "INSERT INTO block_items (block_id,type,lesson_id,task_id,title,order_index) "
            "VALUES (?,?,NULL,?,?,4)",
            (block_id, 'task', task3_id, '1')
        )

        print(f'Создан курс «{title}»')
        return course_id

    open_course_id   = make_course('Open Course 1',   'Open Course 1',   is_open=True)
    closed_course_id = make_course('Closed Course 1', 'Closed Course 1', is_open=False)

    # ── Enrol students ────────────────────────────────────────────
    db.execute("INSERT OR IGNORE INTO user_courses (user_id,course_id) VALUES (?,?)",
               (s1_id, open_course_id))
    db.execute("INSERT OR IGNORE INTO user_courses (user_id,course_id) VALUES (?,?)",
               (s2_id, closed_course_id))


def init_db():
    with app.app_context():
        os.makedirs(app.instance_path, exist_ok=True)
        db = get_db()
        check_and_create_tables(db)
        seed_default_data(db)
        db.commit()


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)