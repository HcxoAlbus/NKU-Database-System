import os
import mysql.connector
from mysql.connector import Error
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, get_flashed_messages # 添加 get_flashed_messages
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime as dt, timedelta # 添加 timedelta
import math # 添加 math

load_dotenv() # 加载 .env 文件中的环境变量

app = Flask(__name__) # 创建 Flask 应用实例

# 设置一个安全的密钥用于 session 管理
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'a_very_secret_key_for_development_12345') # 最好从环境变量读取

# --- 数据库连接配置 ---
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_DATABASE = os.getenv('DB_DATABASE', 'campus_activities')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

def get_db_connection():
    """创建并返回MySQL数据库连接"""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            database=DB_DATABASE,
            user=DB_USER,
            password=DB_PASSWORD,
            # 添加 charset 以确保正确处理中文字符
            charset='utf8mb4'
        )
        if conn.is_connected():
            # print("数据库连接成功") # 可以取消注释用于调试
            return conn
    except Error as e:
        print(f"数据库连接失败: {e}")
        flash("数据库连接失败，请稍后重试。", "error")
        return None

def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False):
    """执行数据库查询，并处理可能的触发器错误"""
    conn = get_db_connection()
    if conn is None:
        return None # 连接失败

    cursor = conn.cursor(dictionary=True)
    result = None
    try:
        cursor.execute(query, params)
        if commit:
            conn.commit()
            # 对于 INSERT/UPDATE/DELETE，可以考虑返回 True 表示成功，但目前保持不变
            result = cursor.lastrowid if cursor.lastrowid else True # 稍微改进，返回 True 表示提交成功
        elif fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
        # 如果只是执行 DDL 或不需要返回结果的 DML，result 会是 None
    except Error as e:
        print(f"执行查询时出错: {e}")
        print(f"查询语句: {query}")
        print(f"参数: {params}")
        error_message = str(e)
        # 提取更具体的错误信息给用户
        user_friendly_message = "数据库操作失败，请稍后重试。"
        if "报名人数已满" in error_message:
            user_friendly_message = '错误：该活动报名人数已满。'
        elif "不接受报名" in error_message:
             user_friendly_message = '错误：该活动当前不接受报名。'
        elif "已有其他活动安排" in error_message:
             user_friendly_message = '错误：该时间段内此地点已有其他活动安排。'
        elif "开始时间必须早于结束时间" in error_message:
             user_friendly_message = '错误：活动开始时间必须早于结束时间。'
        elif "容量不能为负数" in error_message:
             user_friendly_message = '错误：活动容量不能为负数。'
        elif "Duplicate entry" in error_message and "unique_registration" in error_message:
             user_friendly_message = '错误：您已经报名过此活动。'
        elif "Duplicate entry" in error_message and "unique_feedback" in error_message:
             user_friendly_message = '错误：您已经反馈过此活动。'
        elif "FOREIGN KEY constraint fails" in error_message:
             user_friendly_message = '错误：操作涉及的数据不存在或已被删除。'

        flash(user_friendly_message, "error")
        if conn.is_connected():
             conn.rollback() # 回滚事务
        result = None # 返回 None 表示操作失败
    finally:
        cursor.close()
        if conn.is_connected():
            conn.close()
            # print("数据库连接已关闭") # 可以取消注释用于调试
    return result

# --- 上下文处理器 ---
@app.context_processor
def inject_now():
    """向所有模板注入当前时间"""
    return {'now': dt.utcnow()} # 使用 UTC 时间或根据需要调整

# --- 基础路由 ---
@app.route('/')
def index():
    """首页，显示近期未开始的活动"""
    query = """
        SELECT a.ActivityID, a.Name, a.StartTime, l.Name as LocationName
        FROM Activities a
        LEFT JOIN Locations l ON a.LocationID = l.LocationID
        WHERE a.Status = '未开始' AND a.StartTime >= CURDATE()
        ORDER BY a.StartTime ASC
        LIMIT 5
    """
    activities = execute_query(query, fetchall=True)
    return render_template('index.html', activities=activities)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_type = request.form['user_type']
        email = request.form.get('email') # 可选字段
        phone = request.form.get('phone') # 可选字段
        profile_desc = request.form.get('profile_description') # 可选字段
        interest_ids = request.form.getlist('interests') # 获取选中的兴趣ID列表

        # 检查用户名是否已存在
        user_exists = execute_query("SELECT UserID FROM Users WHERE Username = %s", (username,), fetchone=True)
        if user_exists:
            flash('用户名已存在，请选择其他用户名。', 'error')
            # 保留用户输入以便重新渲染表单
            return render_template('register.html',
                                   institutes=execute_query("SELECT InstituteID, Name FROM Institutes ORDER BY Name", fetchall=True) or [],
                                   interests=execute_query("SELECT InterestID, Name FROM Interests ORDER BY Name", fetchall=True) or [],
                                   form_data=request.form) # 传递表单数据

        # 密码哈希
        password_hash = generate_password_hash(password)

        # 插入用户基表
        insert_user_query = """
            INSERT INTO Users (Username, PasswordHash, Email, PhoneNumber, UserType, ProfileDescription)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        user_id = execute_query(insert_user_query, (username, password_hash, email, phone, user_type, profile_desc), commit=True)

        if user_id is None or user_id is False: # 检查 execute_query 的返回值
            flash('注册用户时发生错误，请重试。', 'error')
            return render_template('register.html',
                                   institutes=execute_query("SELECT InstituteID, Name FROM Institutes ORDER BY Name", fetchall=True) or [],
                                   interests=execute_query("SELECT InterestID, Name FROM Interests ORDER BY Name", fetchall=True) or [],
                                   form_data=request.form)

        # 根据用户类型插入详细信息表
        success = False
        if user_type == 'student':
            student_id_number = request.form.get('student_id_number')
            institute_id = request.form.get('institute_id') # 需要从表单获取学院ID
            major = request.form.get('major')
            enrollment_year = request.form.get('enrollment_year')
            insert_detail_query = """
                INSERT INTO Students (UserID, StudentIDNumber, InstituteID, Major, EnrollmentYear)
                VALUES (%s, %s, %s, %s, %s)
            """
            success = execute_query(insert_detail_query, (user_id, student_id_number, institute_id, major, enrollment_year), commit=True)
        elif user_type == 'teacher':
            employee_id_number = request.form.get('employee_id_number')
            institute_id = request.form.get('institute_id') # 需要从表单获取单位ID
            title = request.form.get('title')
            insert_detail_query = """
                INSERT INTO Teachers (UserID, EmployeeIDNumber, InstituteID, Title)
                VALUES (%s, %s, %s, %s)
            """
            success = execute_query(insert_detail_query, (user_id, employee_id_number, institute_id, title), commit=True)
        elif user_type == 'external':
            organization = request.form.get('organization') # 需要从表单获取组织
            insert_detail_query = "INSERT INTO ExternalUsers (UserID, Organization) VALUES (%s, %s)"
            success = execute_query(insert_detail_query, (user_id, organization), commit=True)

        if not success:
             # 插入详细信息失败，可能需要回滚或记录错误，但至少提示用户
             flash('注册用户信息不完整，请稍后在个人中心补充。', 'warning')
             # 注意：此时基础用户已创建

        # 插入用户兴趣
        if interest_ids:
            interest_values = [(user_id, int(interest_id)) for interest_id in interest_ids]
            insert_interests_query = "INSERT INTO User_Interests (UserID, InterestID) VALUES (%s, %s)"
            # 使用 executemany 可能更高效，但简单起见，逐条插入
            interest_success = True
            for val in interest_values:
                if not execute_query(insert_interests_query, val, commit=True):
                    interest_success = False
                    break # 一条失败就停止
            if not interest_success:
                 flash('部分兴趣信息保存失败。', 'warning')


        flash('注册成功！请登录。', 'success')
        return redirect(url_for('login'))

    # GET 请求，加载学院和兴趣列表
    institutes = execute_query("SELECT InstituteID, Name FROM Institutes ORDER BY Name", fetchall=True)
    interests = execute_query("SELECT InterestID, Name FROM Interests ORDER BY Name", fetchall=True)
    # 确保传递空的 form_data 以避免模板错误
    return render_template('register.html', institutes=institutes or [], interests=interests or [], form_data={})


@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        query = "SELECT UserID, Username, PasswordHash, UserType FROM Users WHERE Username = %s"
        user = execute_query(query, (username,), fetchone=True)

        if user and check_password_hash(user['PasswordHash'], password):
            session['user_id'] = user['UserID']
            session['username'] = user['Username']
            session['user_type'] = user['UserType']
            flash(f'欢迎回来, {user["Username"]}!', 'success')

            # 更新最后登录时间
            update_login_time_query = "UPDATE Users SET LastLogin = NOW() WHERE UserID = %s"
            execute_query(update_login_time_query, (user['UserID'],), commit=True) # 忽略这里的返回值

            # 检查是否有重定向目标
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误。', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    """用户登出"""
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('user_type', None)
    flash('您已成功退出登录。', 'info')
    return redirect(url_for('index'))

# --- 活动相关路由 ---
@app.route('/activities')
def list_activities():
    """显示所有活动列表"""
    query = """
        SELECT a.ActivityID, a.Name, a.StartTime, a.Status, a.Capacity, l.Name as LocationName
        FROM Activities a
        LEFT JOIN Locations l ON a.LocationID = l.LocationID
        ORDER BY a.StartTime DESC -- 按开始时间降序排列
    """
    activities = execute_query(query, fetchall=True)
    return render_template('activity_list.html', activities=activities)

@app.route('/activity/<int:activity_id>')
def activity_detail(activity_id):
    """显示单个活动的详细信息"""
    # ... (查询 activity 的代码保持不变) ...
    query = """
        SELECT
            a.*,
            l.Name AS LocationName,
            l.Address AS LocationAddress,
            u.Username AS ManagerName,
            GROUP_CONCAT(DISTINCT c.Name ORDER BY c.Name SEPARATOR ', ') AS Categories,
            GROUP_CONCAT(DISTINCT i.Name ORDER BY i.Name SEPARATOR ', ') AS Organizers
        FROM Activities a
        LEFT JOIN Locations l ON a.LocationID = l.LocationID
        LEFT JOIN Users u ON a.ManagerUserID = u.UserID
        LEFT JOIN Activity_Categories ac ON a.ActivityID = ac.ActivityID
        LEFT JOIN Categories c ON ac.CategoryID = c.CategoryID
        LEFT JOIN Organizers o ON a.ActivityID = o.ActivityID
        LEFT JOIN Institutes i ON o.InstituteID = i.InstituteID
        WHERE a.ActivityID = %s
        GROUP BY a.ActivityID
    """
    activity = execute_query(query, (activity_id,), fetchone=True)

    if not activity:
        flash('未找到该活动。', 'error')
        return redirect(url_for('list_activities'))

    # 查询当前报名人数
    reg_count_query = "SELECT COUNT(*) as count FROM Registrations WHERE ActivityID = %s AND Status = '已报名'"
    reg_count_result = execute_query(reg_count_query, (activity_id,), fetchone=True)
    registration_count = reg_count_result['count'] if reg_count_result else 0

    # 检查当前用户是否已报名
    user_registered = False
    if 'user_id' in session:
        check_reg_query = "SELECT 1 FROM Registrations WHERE UserID = %s AND ActivityID = %s AND Status = '已报名'"
        user_registered = execute_query(check_reg_query, (session['user_id'], activity_id), fetchone=True) is not None

    # --- 新增：计算是否可以报名 ---
    can_register = False
    if activity['Status'] == '未开始':
        if activity['Capacity'] == 0: # 容量不限
            can_register = True
        elif activity['Capacity'] > 0 and registration_count < activity['Capacity']:
            can_register = True
    # --- 结束新增 ---

    return render_template('activity_detail.html',
                           activity=activity,
                           registration_count=registration_count,
                           user_registered=user_registered,
                           can_register=can_register) # <--- 传递 can_register
@app.route('/activity/<int:activity_id>/register', methods=['POST'])
def register_activity(activity_id):
    """处理用户报名活动的请求 (触发器负责最终校验)"""
    if 'user_id' not in session:
        flash('请先登录再报名。', 'warning')
        return redirect(url_for('login', next=url_for('activity_detail', activity_id=activity_id)))

    user_id = session['user_id']

    # (可选) 应用层预检查，提高用户体验，但触发器是最终保障
    query_activity_status = "SELECT Status, Capacity FROM Activities WHERE ActivityID = %s"
    activity_info = execute_query(query_activity_status, (activity_id,), fetchone=True)

    if not activity_info:
        flash('活动不存在。', 'error')
        return redirect(url_for('list_activities'))

    if activity_info['Status'] != '未开始':
        flash('该活动当前不接受报名。', 'warning')
        return redirect(url_for('activity_detail', activity_id=activity_id))

    # 尝试插入报名记录 - 触发器将在此执行检查
    insert_reg_query = """
        INSERT INTO Registrations (UserID, ActivityID, Status)
        VALUES (%s, %s, '已报名')
        ON DUPLICATE KEY UPDATE Status = '已报名' -- 如果已取消报名，允许重新报名
    """
    registration_result = execute_query(insert_reg_query, (user_id, activity_id), commit=True)

    # 检查插入是否成功 (execute_query 在触发器报错时返回 None 或 False)
    if registration_result: # 成功时返回 True 或 lastrowid
        flash('报名成功！', 'success')
    # else: # 错误消息已由 execute_query 中的 flash 处理

    return redirect(url_for('activity_detail', activity_id=activity_id))


@app.route('/activity/<int:activity_id>/cancel_registration', methods=['POST'])
def cancel_registration(activity_id):
    """用户取消报名"""
    if 'user_id' not in session:
        flash('请先登录。', 'warning')
        # 重定向回活动详情页可能更合适
        return redirect(url_for('login', next=url_for('activity_detail', activity_id=activity_id)))

    user_id = session['user_id']

    # 检查活动状态，通常只有未开始的活动可以取消报名
    activity_status_query = "SELECT Status FROM Activities WHERE ActivityID = %s"
    activity_info = execute_query(activity_status_query, (activity_id,), fetchone=True)

    if not activity_info:
        flash('活动不存在。', 'error')
        # 如果活动不存在，重定向到列表页或个人中心
        return redirect(url_for('profile')) # 或者 list_activities

    if activity_info['Status'] != '未开始':
        flash('该活动已开始或结束，无法取消报名。', 'warning')
        # 即使不能取消，也留在详情页
        return redirect(url_for('activity_detail', activity_id=activity_id))

    # 更新报名状态为 '已取消'
    update_query = """
        UPDATE Registrations
        SET Status = '已取消'
        WHERE UserID = %s AND ActivityID = %s AND Status = '已报名'
    """
    # 这里需要检查影响的行数来确认是否真的取消了
    conn = get_db_connection()
    if conn is None:
        return redirect(url_for('activity_detail', activity_id=activity_id)) # flash 消息已在 get_db_connection 设置

    cursor = conn.cursor()
    try:
        cursor.execute(update_query, (user_id, activity_id))
        affected_rows = cursor.rowcount # 获取影响的行数
        conn.commit()
        if affected_rows > 0:
            flash('已成功取消报名。', 'success')
        else:
            # 可能用户并未报名，或者状态不是'已报名'
            flash('未能取消报名（可能您未报名或状态已改变）。', 'info')
    except Error as e:
        print(f"取消报名时出错: {e}")
        flash('取消报名时发生错误，请重试。', 'error')
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    # 不论成功与否，都重定向回个人中心页面，因为按钮在那里
    return redirect(url_for('profile'))

# --- 编辑活动的路由和处理函数 ---
@app.route('/activity/<int:activity_id>/edit', methods=['GET', 'POST'])
def edit_activity(activity_id):
    """显示编辑活动表单并处理提交"""
    if 'user_id' not in session:
        flash('请先登录以编辑活动。', 'warning')
        return redirect(url_for('login', next=request.url))

    user_id = session['user_id']

    # --- POST 请求：处理表单提交 ---
    if request.method == 'POST':
        # 1. 获取表单数据
        name = request.form.get('name')
        description = request.form.get('description')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        location_id_str = request.form.get('location_id')
        capacity_str = request.form.get('capacity')
        requirements = request.form.get('requirements')
        # 类别和主办方更新逻辑 (如果需要)
        # category_ids = request.form.getlist('categories')
        # organizer_ids = request.form.getlist('organizers')

        # 2. 基本验证 (应用层)
        if not all([name, start_time_str, end_time_str, location_id_str, capacity_str]):
            flash('请填写所有必填字段。', 'error')
            # 需要重新加载编辑页面所需的数据并返回
            # (为了简洁，这里省略了重新加载数据的代码，实际应重新查询并渲染)
            return redirect(url_for('edit_activity', activity_id=activity_id))

        try:
            start_time = dt.strptime(start_time_str, '%Y-%m-%dT%H:%M')
            end_time = dt.strptime(end_time_str, '%Y-%m-%dT%H:%M')
            location_id = int(location_id_str) if location_id_str else None
            capacity = int(capacity_str)
        except ValueError:
            flash('日期时间格式或数字格式无效。', 'error')
            return redirect(url_for('edit_activity', activity_id=activity_id))

        # 3. 调用存储过程执行更新 (包含权限验证和冲突检查)
        proc_params = (
            activity_id, user_id, name, description, start_time,
            end_time, location_id, capacity, requirements
        )
        update_success = execute_query("CALL UpdateActivityDetails(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                       proc_params, commit=True)

        # 4. 处理结果
        if update_success is not None: # execute_query 成功时不返回特定值，失败时返回 None
            flash('活动信息更新成功！', 'success')
            # TODO: 更新 Activity_Categories 和 Organizers (如果需要)
            # 这通常涉及先删除旧关联，再插入新关联，建议在事务中完成或另写存储过程
            return redirect(url_for('activity_detail', activity_id=activity_id))
        else:
            # 错误消息已由 execute_query 中的 flash 处理
            # 重新渲染编辑页面，并可能需要传递旧的表单数据以供用户修正
            # (为了简洁，这里仅重定向，实际应用中可能需要更好的错误处理流程)
             # 重新加载数据并渲染编辑页，保留用户输入
            activity_data = request.form.to_dict()
            # 将 datetime-local 字符串格式转换回存储过程或模型期望的格式可能需要处理
            # 或者直接传递字符串让模板处理
            activity_data['start_time'] = start_time_str
            activity_data['end_time'] = end_time_str
            # 重新获取下拉列表等数据
            locations = execute_query("SELECT LocationID, Name FROM Locations ORDER BY Name", fetchall=True)
            # categories = execute_query("SELECT CategoryID, Name FROM Categories ORDER BY Name", fetchall=True)
            # organizers = execute_query("SELECT InstituteID, Name FROM Institutes ORDER BY Name", fetchall=True)
            flash('更新失败，请检查输入或错误信息。', 'error') # 补充一个通用错误提示
            return render_template('edit_activity.html',
                                   activity=activity_data, # 传递包含用户输入的字典
                                   activity_id=activity_id,
                                   locations=locations or [],
                                   # categories=categories or [], # 如果需要编辑类别
                                   # organizers=organizers or [], # 如果需要编辑主办方
                                   form_data=activity_data) # 用于填充表单

    # --- GET 请求：显示编辑表单 ---
    else:
        # 1. 查询活动当前信息
        query = """
            SELECT a.*, l.Name AS LocationName
            FROM Activities a
            LEFT JOIN Locations l ON a.LocationID = l.LocationID
            WHERE a.ActivityID = %s
        """
        activity = execute_query(query, (activity_id,), fetchone=True)

        if not activity:
            flash('未找到该活动。', 'error')
            return redirect(url_for('list_activities'))

        # 2. 验证用户权限
        if activity['ManagerUserID'] != user_id:
            flash('您无权编辑此活动。', 'error')
            return redirect(url_for('activity_detail', activity_id=activity_id))

        # 3. 查询编辑表单所需的其他数据 (地点列表等)
        locations = execute_query("SELECT LocationID, Name FROM Locations ORDER BY Name", fetchall=True)
        # categories = execute_query("SELECT CategoryID, Name FROM Categories ORDER BY Name", fetchall=True) # 如果需要编辑类别
        # organizers = execute_query("SELECT InstituteID, Name FROM Institutes ORDER BY Name", fetchall=True) # 如果需要编辑主办方
        # current_category_ids = ... # 查询当前活动关联的类别ID
        # current_organizer_ids = ... # 查询当前活动关联的主办方ID

        # 格式化 datetime 以适配 datetime-local input
        if activity.get('StartTime'):
            activity['start_time_str'] = activity['StartTime'].strftime('%Y-%m-%dT%H:%M')
        if activity.get('EndTime'):
            activity['end_time_str'] = activity['EndTime'].strftime('%Y-%m-%dT%H:%M')


        return render_template('edit_activity.html',
                               activity=activity,
                               activity_id=activity_id,
                               locations=locations or [],
                               # categories=categories or [], # 传递类别列表
                               # organizers=organizers or [], # 传递主办方列表
                               # current_category_ids=current_category_ids, # 传递当前选中的类别
                               # current_organizer_ids=current_organizer_ids, # 传递当前选中的主办方
                               form_data=activity # 初始表单数据
                              )
    
@app.route('/activity/create', methods=['GET', 'POST'])
def create_activity():
    """显示创建活动表单并处理提交"""
    if 'user_id' not in session:
        flash('请先登录才能创建活动。', 'warning')
        return redirect(url_for('login', next=url_for('create_activity')))

    # --- POST 请求：处理表单提交 ---
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        location_id = request.form.get('location_id')
        capacity_str = request.form.get('capacity', '0') # 默认为 '0'
        requirements = request.form.get('requirements')
        category_ids = request.form.getlist('categories') # 多选
        organizer_ids = request.form.getlist('organizers') # 多选
        manager_user_id = session['user_id'] # 当前登录用户为负责人

        # --- 数据验证 ---
        errors = {}
        if not name: errors['name'] = '活动名称不能为空。'
        if not start_time_str: errors['start_time'] = '开始时间不能为空。'
        if not end_time_str: errors['end_time'] = '结束时间不能为空。'
        if not location_id: errors['location_id'] = '活动地点不能为空。'

        start_time, end_time = None, None
        try:
            if start_time_str: start_time = dt.fromisoformat(start_time_str)
            if end_time_str: end_time = dt.fromisoformat(end_time_str)
            if start_time and end_time and start_time >= end_time:
                errors['time_logic'] = '结束时间必须晚于开始时间。'
        except ValueError:
            errors['time_format'] = '时间格式无效。'

        capacity = 0
        try:
            capacity = int(capacity_str)
            if capacity < 0:
                errors['capacity'] = '容量不能为负数。'
        except ValueError:
            errors['capacity'] = '容量必须是数字。'

        if errors:
            for error_msg in errors.values():
                flash(error_msg, 'error')
            # 重新加载页面所需数据并渲染模板，回填表单
            locations = execute_query("SELECT LocationID, Name FROM Locations ORDER BY Name", fetchall=True)
            categories = execute_query("SELECT CategoryID, Name FROM Categories ORDER BY Name", fetchall=True)
            organizers = execute_query("SELECT InstituteID, Name FROM Institutes ORDER BY Name", fetchall=True)
            return render_template('create_activity.html',
                                   locations=locations or [],
                                   categories=categories or [],
                                   organizers=organizers or [],
                                   form_data=request.form) # 传递原始表单数据

        # --- 插入数据库 ---
        insert_activity_query = """
            INSERT INTO Activities (Name, Description, StartTime, EndTime, LocationID, ManagerUserID, Capacity, Requirements, Status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '未开始')
        """
        activity_id = execute_query(insert_activity_query,
                                    (name, description, start_time, end_time, location_id, manager_user_id, capacity, requirements),
                                    commit=True)

        if not activity_id: # 如果 execute_query 返回 None 或 False
            # flash 消息已在 execute_query 中设置
            # 重新加载页面所需数据并渲染模板，回填表单
            locations = execute_query("SELECT LocationID, Name FROM Locations ORDER BY Name", fetchall=True)
            categories = execute_query("SELECT CategoryID, Name FROM Categories ORDER BY Name", fetchall=True)
            organizers = execute_query("SELECT InstituteID, Name FROM Institutes ORDER BY Name", fetchall=True)
            return render_template('create_activity.html',
                                   locations=locations or [],
                                   categories=categories or [],
                                   organizers=organizers or [],
                                   form_data=request.form)

        # 插入关联表数据 (类别和主办方)
        activity_created_successfully = True # 假设活动主体创建成功

        if category_ids:
            cat_values = [(activity_id, int(cat_id)) for cat_id in category_ids]
            insert_cat_query = "INSERT INTO Activity_Categories (ActivityID, CategoryID) VALUES (%s, %s)"
            for val in cat_values:
                if not execute_query(insert_cat_query, val, commit=True):
                    flash(f'添加类别时出错 (ID: {val[1]})。', 'warning')
                    activity_created_successfully = False # 标记有部分失败

        if organizer_ids:
            org_values = [(activity_id, int(org_id)) for org_id in organizer_ids]
            insert_org_query = "INSERT INTO Organizers (ActivityID, InstituteID) VALUES (%s, %s)"
            for val in org_values:
                if not execute_query(insert_org_query, val, commit=True):
                    flash(f'添加主办方时出错 (ID: {val[1]})。', 'warning')
                    activity_created_successfully = False # 标记有部分失败

        if activity_created_successfully:
             flash('活动创建成功！', 'success')
             return redirect(url_for('activity_detail', activity_id=activity_id))
        else:
             flash('活动主体已创建，但部分关联信息（类别/主办方）添加失败。请稍后编辑活动。', 'warning')
             return redirect(url_for('activity_detail', activity_id=activity_id)) # 仍然跳转到详情页

    # --- GET 请求：显示表单 ---
    else: # request.method == 'GET'
        locations = execute_query("SELECT LocationID, Name FROM Locations ORDER BY Name", fetchall=True)
        categories = execute_query("SELECT CategoryID, Name FROM Categories ORDER BY Name", fetchall=True)
        organizers = execute_query("SELECT InstituteID, Name FROM Institutes ORDER BY Name", fetchall=True) # 主办方是学院
        # 确保传递空的 form_data
        return render_template('create_activity.html',
                               locations=locations or [],
                               categories=categories or [],
                               organizers=organizers or [],
                               form_data={})

# --- 删除活动的路由和处理函数 ---
@app.route('/activity/<int:activity_id>/delete', methods=['POST'])
def delete_activity(activity_id):
    """删除活动 (物理删除)"""
    if 'user_id' not in session:
        flash('请先登录。', 'warning')
        return redirect(url_for('login'))

    # 验证当前用户是否是活动的负责人
    activity_query = "SELECT ManagerUserID FROM Activities WHERE ActivityID = %s"
    activity = execute_query(activity_query, (activity_id,), fetchone=True)

    if not activity:
        flash('活动不存在。', 'error')
        return redirect(url_for('profile')) # 或者 list_activities

    if activity['ManagerUserID'] != session['user_id']:
        flash('您没有权限删除此活动。', 'error')
        return redirect(url_for('activity_detail', activity_id=activity_id))

    # --- 执行物理删除 ---
    # 由于设置了外键的 ON DELETE CASCADE，删除 Activities 表的记录会自动删除 Registrations, Feedbacks, Activity_Categories, Organizers 中的相关记录
    delete_query = "DELETE FROM Activities WHERE ActivityID = %s"
    delete_result = execute_query(delete_query, (activity_id,), commit=True)

    # 检查结果
    if delete_result: # 成功时返回 True
        flash('活动已成功删除。', 'success')
        return redirect(url_for('profile')) # 删除后返回个人中心
    else:
        # flash 消息已在 execute_query 中设置
        # 留在详情页（虽然它可能已经不存在了），或者重定向到个人中心
        return redirect(url_for('profile'))


@app.route('/activities/nearby')
def nearby_activities():
    """显示用户附近未开始的活动"""
    if 'user_id' not in session:
        flash('请先登录以查看附近活动。', 'warning')
        return redirect(url_for('login', next=url_for('nearby_activities')))

    user_id = session['user_id']
    # 获取用户当前位置
    user_location_query = "SELECT CurrentLatitude, CurrentLongitude FROM Users WHERE UserID = %s"
    user_loc = execute_query(user_location_query, (user_id,), fetchone=True)

    if not user_loc or user_loc.get('CurrentLatitude') is None or user_loc.get('CurrentLongitude') is None:
        flash('无法获取您的当前位置信息，请先在个人中心更新。', 'info')
        # 可以重定向到个人中心，或者显示一个提示页面
        return redirect(url_for('profile')) # 重定向到个人中心让用户更新

    user_lat = user_loc['CurrentLatitude']
    user_lon = user_loc['CurrentLongitude']
    radius_km = 5 # 默认搜索半径 5 公里

    # 查询所有未开始且有地理位置的活动
    nearby_query = """
        SELECT a.ActivityID, a.Name, a.StartTime, a.Status, a.Capacity,
               l.Name as LocationName, l.Latitude, l.Longitude
        FROM Activities a
        JOIN Locations l ON a.LocationID = l.LocationID
        WHERE a.Status = '未开始' AND a.StartTime >= NOW()
          AND l.Latitude IS NOT NULL AND l.Longitude IS NOT NULL
    """
    all_upcoming_activities = execute_query(nearby_query, fetchall=True)

    nearby_list = []
    if all_upcoming_activities:
        for activity in all_upcoming_activities:
            # 确保活动有经纬度才计算距离
            if activity.get('Latitude') is not None and activity.get('Longitude') is not None:
                distance = calculate_haversine(user_lat, user_lon, activity['Latitude'], activity['Longitude'])
                if distance is not None and distance <= radius_km:
                    activity['distance'] = distance # 添加距离信息
                    nearby_list.append(activity)

        # 按距离排序
        nearby_list.sort(key=lambda x: x.get('distance', float('inf')))

    return render_template('activity_list_nearby.html',
                           activities=nearby_list,
                           user_lat=user_lat,
                           user_lon=user_lon,
                           radius=radius_km)


# --- 用户个人中心 ---
@app.route('/profile')
def profile():
    """显示用户个人中心"""
    if 'user_id' not in session:
        flash('请先登录。', 'warning')
        return redirect(url_for('login', next=url_for('profile')))

    user_id = session['user_id']

    # 查询用户基本信息和详细信息
    user_query = """
        SELECT u.UserID, u.Username, u.Email, u.PhoneNumber, u.UserType, u.ProfileDescription,
               u.CurrentLatitude, u.CurrentLongitude,
               s.StudentIDNumber, s.Major, s.EnrollmentYear, si.Name AS StudentInstitute,
               t.EmployeeIDNumber, t.Title, ti.Name AS TeacherInstitute,
               e.Organization
        FROM Users u
        LEFT JOIN Students s ON u.UserID = s.UserID LEFT JOIN Institutes si ON s.InstituteID = si.InstituteID
        LEFT JOIN Teachers t ON u.UserID = t.UserID LEFT JOIN Institutes ti ON t.InstituteID = ti.InstituteID
        LEFT JOIN ExternalUsers e ON u.UserID = e.UserID
        WHERE u.UserID = %s
    """
    user_info = execute_query(user_query, (user_id,), fetchone=True)

    # --- 增加检查 ---
    if not user_info:
        flash('无法加载用户信息，请重新登录。', 'error')
        session.pop('user_id', None) # 清除可能无效的 session
        session.pop('username', None)
        session.pop('user_type', None)
        return redirect(url_for('login'))
    # --- 结束检查 ---

    # 查询用户报名的活动 (未取消的)
    registered_query = """
        SELECT a.ActivityID, a.Name, a.StartTime, r.Status
        FROM Registrations r
        JOIN Activities a ON r.ActivityID = a.ActivityID
        WHERE r.UserID = %s AND r.Status IN ('已报名', '已签到', '未签到')
        ORDER BY a.StartTime DESC
    """
    registered_activities = execute_query(registered_query, (user_id,), fetchall=True)

    # 查询用户管理的活动
    managed_query = """
        SELECT ActivityID, Name, StartTime, Status
        FROM Activities
        WHERE ManagerUserID = %s
        ORDER BY StartTime DESC
    """
    managed_activities = execute_query(managed_query, (user_id,), fetchall=True)


    # 查询所有兴趣和用户已选兴趣
    all_interests_query = "SELECT InterestID, Name FROM Interests ORDER BY Name"
    all_interests = execute_query(all_interests_query, fetchall=True)
    user_interests_query = "SELECT InterestID FROM User_Interests WHERE UserID = %s"
    user_interest_rows = execute_query(user_interests_query, (user_id,), fetchall=True)
    user_interest_ids = {row['InterestID'] for row in user_interest_rows} if user_interest_rows else set()

    # 获取推荐活动
    # 确保传递有效的经纬度给 get_recommendations
    user_lat = user_info.get('CurrentLatitude')
    user_lon = user_info.get('CurrentLongitude')
    recommendations = get_recommendations(user_id, user_lat, user_lon)

    return render_template('profile.html',
                           user=user_info,
                           registered_activities=registered_activities or [],
                           managed_activities=managed_activities or [],
                           all_interests=all_interests or [],
                           user_interest_ids=user_interest_ids,
                           recommendations=recommendations or [])


def get_recommendations(user_id, user_lat=None, user_lon=None):
    """获取活动推荐 (基于兴趣和/或地理位置)"""
    recommendations = []
    seen_ids = set() # 用于去重

    # 1. 基于兴趣推荐
    # 注意：这里的 LIKE 匹配可能不准确，更好的方式是建立 Category 和 Interest 的关联，或者使用更复杂的文本匹配
    interest_based_query = """
        SELECT DISTINCT a.ActivityID, a.Name, a.StartTime, l.Name as LocationName, l.Latitude, l.Longitude
        FROM Activities a
        JOIN Activity_Categories ac ON a.ActivityID = ac.ActivityID
        JOIN Categories c ON ac.CategoryID = c.CategoryID
        JOIN User_Interests ui ON ui.UserID = %s
        JOIN Interests i ON ui.InterestID = i.InterestID
        LEFT JOIN Locations l ON a.LocationID = l.LocationID
        WHERE c.Name LIKE CONCAT('%%', i.Name, '%%') -- 简单模糊匹配
          AND a.Status = '未开始'
          AND a.StartTime >= NOW()
          AND a.ActivityID NOT IN (SELECT ActivityID FROM Registrations WHERE UserID = %s AND Status IN ('已报名', '已签到'))
        ORDER BY a.StartTime ASC
        LIMIT 5
    """
    interest_recs = execute_query(interest_based_query, (user_id, user_id), fetchall=True)
    if interest_recs:
        for rec in interest_recs:
            if rec['ActivityID'] not in seen_ids:
                recommendations.append(rec)
                seen_ids.add(rec['ActivityID'])

    # 2. 基于地理位置推荐 (如果兴趣推荐不足5个，补充附近的)
    needed = 5 - len(recommendations)
    if needed > 0 and user_lat is not None and user_lon is not None:
        radius_km = 10 # 推荐时使用稍大半径

        # 构建排除已推荐活动的 ID 列表和占位符
        excluded_ids = list(seen_ids)
        placeholders = ', '.join(['%s'] * len(excluded_ids)) if excluded_ids else 'NULL' # 使用 NULL 作为占位符

        nearby_query = f"""
            SELECT a.ActivityID, a.Name, a.StartTime, l.Name as LocationName, l.Latitude, l.Longitude
            FROM Activities a
            JOIN Locations l ON a.LocationID = l.LocationID
            WHERE a.Status = '未开始' AND a.StartTime >= NOW()
              AND l.Latitude IS NOT NULL AND l.Longitude IS NOT NULL
              AND a.ActivityID NOT IN (SELECT ActivityID FROM Registrations WHERE UserID = %s AND Status IN ('已报名', '已签到'))
              AND a.ActivityID NOT IN ({placeholders})
            ORDER BY a.StartTime ASC
        """
        # 参数包含 user_id 和所有要排除的 activity_id
        params = [user_id] + excluded_ids

        potential_nearby = execute_query(nearby_query, tuple(params), fetchall=True)

        if potential_nearby:
            nearby_with_distance = []
            for activity in potential_nearby:
                 if activity.get('Latitude') is not None and activity.get('Longitude') is not None:
                    distance = calculate_haversine(user_lat, user_lon, activity['Latitude'], activity['Longitude'])
                    if distance is not None and distance <= radius_km:
                        activity['distance'] = distance
                        nearby_with_distance.append(activity)

            # 按距离排序
            nearby_with_distance.sort(key=lambda x: x.get('distance', float('inf')))

            # 添加到推荐列表，直到满5个或没有更多附近的活动
            for rec in nearby_with_distance:
                if len(recommendations) >= 5:
                    break
                if rec['ActivityID'] not in seen_ids:
                    recommendations.append(rec)
                    seen_ids.add(rec['ActivityID'])

    # 如果仍然不足5个，可以考虑推荐热门活动或最新活动作为补充 (此处省略)

    return recommendations


@app.route('/profile/update', methods=['POST'])
def update_profile():
    """更新用户基本信息和兴趣"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '用户未登录'}), 401 # 应该重定向或返回错误页，这里暂用 JSON

    user_id = session['user_id']
    email = request.form.get('email')
    phone = request.form.get('phone')
    profile_desc = request.form.get('profile_description')
    interest_ids = set(request.form.getlist('interests')) # 获取新选择的兴趣ID集合

    # 更新 Users 表的基本信息
    update_user_query = """
        UPDATE Users
        SET Email = %s, PhoneNumber = %s, ProfileDescription = %s
        WHERE UserID = %s
    """
    update_user_result = execute_query(update_user_query, (email, phone, profile_desc, user_id), commit=True)

    if not update_user_result:
        # flash 消息已在 execute_query 设置
        return redirect(url_for('profile')) # 更新失败，留在个人中心

    # 更新用户兴趣
    # 1. 获取用户当前的兴趣
    current_interests_query = "SELECT InterestID FROM User_Interests WHERE UserID = %s"
    current_interest_rows = execute_query(current_interests_query, (user_id,), fetchall=True)
    current_interest_ids = {str(row['InterestID']) for row in current_interest_rows} if current_interest_rows else set()

    # 2. 计算需要删除和添加的兴趣
    interests_to_add = interest_ids - current_interest_ids
    interests_to_delete = current_interest_ids - interest_ids

    interest_update_success = True

    # 3. 删除不再选择的兴趣
    if interests_to_delete:
        delete_placeholders = ', '.join(['%s'] * len(interests_to_delete))
        delete_interests_query = f"DELETE FROM User_Interests WHERE UserID = %s AND InterestID IN ({delete_placeholders})"
        delete_params = [user_id] + list(interests_to_delete)
        if not execute_query(delete_interests_query, tuple(delete_params), commit=True):
            interest_update_success = False

    # 4. 添加新选择的兴趣
    if interests_to_add:
        add_interest_query = "INSERT INTO User_Interests (UserID, InterestID) VALUES (%s, %s)"
        for interest_id in interests_to_add:
            if not execute_query(add_interest_query, (user_id, int(interest_id)), commit=True):
                interest_update_success = False
                # 可以选择 break 或者继续尝试添加其他的

    if update_user_result and interest_update_success:
        flash('个人信息更新成功！', 'success')
    elif update_user_result and not interest_update_success:
        flash('基本信息更新成功，但兴趣更新时遇到问题。', 'warning')
    # else: 基本信息更新失败的 flash 已被设置

    return redirect(url_for('profile'))


@app.route('/profile/update_location', methods=['POST'])
def update_location():
    """更新用户当前位置 (AJAX)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '用户未登录'}), 401

    user_id = session['user_id']
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')

    if latitude is None or longitude is None:
        return jsonify({'success': False, 'message': '缺少经纬度信息'}), 400

    try:
        lat = float(latitude)
        lon = float(longitude)
        # 可以添加范围校验
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
             raise ValueError("经纬度超出范围")
    except ValueError as e:
        print(f"无效的经纬度: {latitude}, {longitude} - {e}")
        return jsonify({'success': False, 'message': f'无效的经纬度格式: {e}'}), 400

    update_query = """
        UPDATE Users
        SET CurrentLatitude = %s, CurrentLongitude = %s
        WHERE UserID = %s
    """
    update_result = execute_query(update_query, (lat, lon, user_id), commit=True)

    # --- 修改判断逻辑 ---
    if update_result: # execute_query 成功时返回 True
        return jsonify({'success': True, 'message': '位置已更新'})
    else:
        # execute_query 返回 None 或 False 表示失败，flash 消息已设置
        # 尝试获取 flash 消息返回给前端
        messages = get_flashed_messages(category_filter=["error"])
        # flash 消息是给下一个请求的，这里直接获取可能为空
        # 因此，返回一个通用的数据库错误消息
        error_message = "数据库更新时出错" # 默认消息
        # 如果能可靠地从某处获取 execute_query 的具体错误当然更好
        return jsonify({'success': False, 'message': error_message}), 500


def calculate_haversine(lat1, lon1, lat2, lon2):
    """使用 Haversine 公式计算两点间距离 (公里)"""
    R = 6371 # 地球半径 (公里)
    try:
        # 确保输入是浮点数
        lat1_rad = math.radians(float(lat1))
        lon1_rad = math.radians(float(lon1))
        lat2_rad = math.radians(float(lat2))
        lon2_rad = math.radians(float(lon2))

        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad

        a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance = R * c
        return distance
    except (TypeError, ValueError, AttributeError) as e: # 增加 AttributeError
        print(f"计算距离时出错: lat1={lat1}, lon1={lon1}, lat2={lat2}, lon2={lon2} - {e}")
        return None # 返回 None 表示计算失败

# --- 主程序入口 ---
# ... (保持不变) ...

if __name__ == '__main__':
    # 使用环境变量或默认值设置调试模式和端口
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')
    port = int(os.getenv('FLASK_PORT', 5000))
    app.run(debug=debug_mode, port=port, host='0.0.0.0') # 允许外部访问