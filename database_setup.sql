-- 删除旧数据库（如果存在），确保全新开始
DROP DATABASE IF EXISTS campus_activities;

-- 创建新数据库
CREATE DATABASE campus_activities CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE campus_activities;

-- 按依赖关系逆序删除表（如果存在）
DROP TABLE IF EXISTS User_Interests;
DROP TABLE IF EXISTS Organizers;
DROP TABLE IF EXISTS Activity_Categories;
DROP TABLE IF EXISTS Feedbacks;
DROP TABLE IF EXISTS Registrations;
DROP TABLE IF EXISTS ExternalUsers;
DROP TABLE IF EXISTS Teachers;
DROP TABLE IF EXISTS Students;
DROP TABLE IF EXISTS Activities;
DROP TABLE IF EXISTS Interests;
DROP TABLE IF EXISTS Categories;
DROP TABLE IF EXISTS Users;
DROP TABLE IF EXISTS Institutes;
DROP TABLE IF EXISTS Locations;

-- 1. 地点表
CREATE TABLE Locations (
    LocationID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL UNIQUE,
    Address VARCHAR(255),
    Latitude DECIMAL(10, 8), -- 纬度
    Longitude DECIMAL(11, 8), -- 经度
    Description TEXT
);

-- 2. 学院/单位表
CREATE TABLE Institutes (
    InstituteID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL UNIQUE
);

-- 3. 用户基表
CREATE TABLE Users (
    UserID INT AUTO_INCREMENT PRIMARY KEY,
    Username VARCHAR(50) NOT NULL UNIQUE,
    PasswordHash VARCHAR(255) NOT NULL, -- 存储哈希后的密码
    Email VARCHAR(100) UNIQUE,
    PhoneNumber VARCHAR(20),
    UserType ENUM('student', 'teacher', 'external') NOT NULL,
    RegistrationDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    LastLogin TIMESTAMP NULL,
    CurrentLatitude DECIMAL(10, 8) NULL, -- 用户当前纬度
    CurrentLongitude DECIMAL(11, 8) NULL, -- 用户当前经度
    ProfileDescription TEXT NULL -- 个人简介
);

-- 4. 学生表 (继承 Users)
CREATE TABLE Students (
    UserID INT PRIMARY KEY,
    StudentIDNumber VARCHAR(50) UNIQUE, -- 学号
    InstituteID INT, -- 所属学院
    Major VARCHAR(100),
    EnrollmentYear YEAR,
    FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE,
    FOREIGN KEY (InstituteID) REFERENCES Institutes(InstituteID) ON DELETE SET NULL
);

-- 5. 教师表 (继承 Users)
CREATE TABLE Teachers (
    UserID INT PRIMARY KEY,
    EmployeeIDNumber VARCHAR(50) UNIQUE, -- 工号
    InstituteID INT, -- 所属学院/单位
    Title VARCHAR(50), -- 职称
    FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE,
    FOREIGN KEY (InstituteID) REFERENCES Institutes(InstituteID) ON DELETE SET NULL
);

-- 6. 校外人员表 (继承 Users)
CREATE TABLE ExternalUsers (
    UserID INT PRIMARY KEY,
    Organization VARCHAR(100), -- 所属单位/组织
    FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE
);

-- 7. 活动类别表
CREATE TABLE Categories (
    CategoryID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(50) NOT NULL UNIQUE,
    Description TEXT
);

-- 8. 兴趣爱好表
CREATE TABLE Interests (
    InterestID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(50) NOT NULL UNIQUE
);

-- 9. 活动表
CREATE TABLE Activities (
    ActivityID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(150) NOT NULL,
    Description TEXT,
    StartTime DATETIME NOT NULL,
    EndTime DATETIME NOT NULL,
    LocationID INT,
    ManagerUserID INT, -- 活动负责人 (关联到 Users 表)
    Capacity INT DEFAULT 0, -- 容量 (0 表示无限制)
    Status ENUM('未开始', '进行中', '已结束', '已取消') DEFAULT '未开始',
    Requirements TEXT, -- 活动要求
    CreationTime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    LastUpdateTime TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (LocationID) REFERENCES Locations(LocationID) ON DELETE SET NULL,
    FOREIGN KEY (ManagerUserID) REFERENCES Users(UserID) ON DELETE SET NULL,
    CHECK (EndTime > StartTime), -- 结束时间必须晚于开始时间
    CHECK (Capacity >= 0) -- 容量不能为负数
);

-- 10. 活动报名表
CREATE TABLE Registrations (
    RegistrationID INT AUTO_INCREMENT PRIMARY KEY,
    UserID INT NOT NULL,
    ActivityID INT NOT NULL,
    RegistrationTime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    Status ENUM('已报名', '已取消', '已签到', '未签到') DEFAULT '已报名',
    FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE,
    FOREIGN KEY (ActivityID) REFERENCES Activities(ActivityID) ON DELETE CASCADE,
    UNIQUE KEY unique_registration (UserID, ActivityID) -- 一个用户对一个活动只能报名一次
);

-- 11. 活动反馈表
CREATE TABLE Feedbacks (
    FeedbackID INT AUTO_INCREMENT PRIMARY KEY,
    UserID INT NOT NULL,
    ActivityID INT NOT NULL,
    Rating INT CHECK (Rating >= 1 AND Rating <= 5), -- 评分 (1-5)
    Comment TEXT,
    FeedbackTime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE,
    FOREIGN KEY (ActivityID) REFERENCES Activities(ActivityID) ON DELETE CASCADE,
    UNIQUE KEY unique_feedback (UserID, ActivityID) -- 一个用户对一个活动只能反馈一次
);

-- 12. 活动-类别关联表 (多对多)
CREATE TABLE Activity_Categories (
    ActivityID INT NOT NULL,
    CategoryID INT NOT NULL,
    PRIMARY KEY (ActivityID, CategoryID),
    FOREIGN KEY (ActivityID) REFERENCES Activities(ActivityID) ON DELETE CASCADE,
    FOREIGN KEY (CategoryID) REFERENCES Categories(CategoryID) ON DELETE CASCADE
);

-- 13. 活动-主办方关联表 (多对多, 主办方是学院/单位)
CREATE TABLE Organizers (
    ActivityID INT NOT NULL,
    InstituteID INT NOT NULL,
    PRIMARY KEY (ActivityID, InstituteID),
    FOREIGN KEY (ActivityID) REFERENCES Activities(ActivityID) ON DELETE CASCADE,
    FOREIGN KEY (InstituteID) REFERENCES Institutes(InstituteID) ON DELETE CASCADE
);

-- 14. 用户-兴趣关联表 (多对多)
CREATE TABLE User_Interests (
    UserID INT NOT NULL,
    InterestID INT NOT NULL,
    PRIMARY KEY (UserID, InterestID),
    FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE,
    FOREIGN KEY (InterestID) REFERENCES Interests(InterestID) ON DELETE CASCADE
);

-- --- 添加索引 ---
CREATE INDEX idx_activity_starttime ON Activities (StartTime);
CREATE INDEX idx_activity_location ON Activities (LocationID);
CREATE INDEX idx_location_coords ON Locations (Latitude, Longitude);
CREATE INDEX idx_registration_activity ON Registrations (ActivityID);
CREATE INDEX idx_feedback_activity ON Feedbacks (ActivityID);
CREATE INDEX idx_user_type ON Users (UserType);
CREATE INDEX idx_activity_status ON Activities (Status);

-- --- 插入示例数据 ---

-- 地点
INSERT INTO Locations (Name, Address, Latitude, Longitude, Description) VALUES
('大学生活动中心', '某某路1号', 34.0522, -118.2437, '主校区活动中心'),
('图书馆报告厅', '某某路2号', 34.0530, -118.2440, '位于图书馆一楼'),
('体育馆', '运动场路10号', 34.0500, -118.2500, '室内体育馆'),
('线上会议室', NULL, NULL, NULL, '通过Zoom或腾讯会议进行');

-- 学院/单位
INSERT INTO Institutes (Name) VALUES
('计算机学院'),
('外国语学院'),
('校团委'),
('学生会'),
('物理学院');

-- 活动类别
INSERT INTO Categories (Name, Description) VALUES
('学术讲座', '各类学术性质的讲座'),
('文体娱乐', '体育比赛、文艺晚会等'),
('志愿服务', '校内外志愿活动'),
('社团活动', '学生社团组织的活动'),
('创新创业', '创业讲座、比赛等');

-- 兴趣爱好
INSERT INTO Interests (Name) VALUES
('编程'), ('英语'), ('篮球'), ('音乐'), ('电影'), ('志愿活动'), ('创业'), ('物理学');

-- 用户 (密码都是 'password' 的哈希值)
-- 使用 Python 生成: from werkzeug.security import generate_password_hash; print(generate_password_hash('password'))
-- $pbkdf2-sha256$29000$N9z.qf7Y.a8z.qf7Y.a8z$5a1fdbdb5a1fdbdb5a1fdbdb5a1fdbdb5a1fdbdb5a1fdbdb5a1fdbdb5a1fdbdb (示例哈希)
-- 实际应用中应使用更安全的哈希方法和盐值
INSERT INTO Users (Username, PasswordHash, Email, PhoneNumber, UserType) VALUES
('student1', '$pbkdf2-sha256$600000$Fp8tJqJ8wX9nL3kR$1U/N9yJ8wX9nL3kR1U/N9yJ8wX9nL3kR1U/N9yJ8wX9nL3kR1U/N9yJ8wX9nL3kR', 'student1@test.com', '13800000001', 'student'),
('teacher1', '$pbkdf2-sha256$600000$Fp8tJqJ8wX9nL3kR$1U/N9yJ8wX9nL3kR1U/N9yJ8wX9nL3kR1U/N9yJ8wX9nL3kR1U/N9yJ8wX9nL3kR', 'teacher1@test.com', '13900000001', 'teacher'),
('external1', '$pbkdf2-sha256$600000$Fp8tJqJ8wX9nL3kR$1U/N9yJ8wX9nL3kR1U/N9yJ8wX9nL3kR1U/N9yJ8wX9nL3kR1U/N9yJ8wX9nL3kR', 'external1@company.com', '18600000001', 'external');

-- 学生详细信息
INSERT INTO Students (UserID, StudentIDNumber, InstituteID, Major, EnrollmentYear) VALUES
(1, '20230001', 1, '计算机科学与技术', 2023);

-- 教师详细信息
INSERT INTO Teachers (UserID, EmployeeIDNumber, InstituteID, Title) VALUES
(2, 'T001', 1, '教授');

-- 校外人员详细信息
INSERT INTO ExternalUsers (UserID, Organization) VALUES
(3, '外部合作公司');

-- 活动
INSERT INTO Activities (Name, Description, StartTime, EndTime, LocationID, ManagerUserID, Capacity, Status, Requirements) VALUES
('新生篮球赛', '计算机学院迎新篮球赛', '2025-09-10 14:00:00', '2025-09-10 17:00:00', 3, 2, 50, '未开始', '仅限本校学生'),
('Python入门讲座', '由张教授主讲的Python基础', '2025-09-15 19:00:00', '2025-09-15 21:00:00', 2, 2, 100, '未开始', '无'),
('线上英语角', '每周一次的线上英语交流活动', '2025-09-12 20:00:00', '2025-09-12 21:00:00', 4, 2, 0, '未开始', '需要有Zoom账号'),
('已结束的活动', '这是一个已经结束的活动示例', '2024-05-01 10:00:00', '2024-05-01 12:00:00', 1, 2, 30, '已结束', NULL),
('已取消的活动', '这是一个被取消的活动示例', '2025-10-01 10:00:00', '2025-10-01 12:00:00', 1, 2, 30, '已取消', NULL);


-- 活动-类别关联
INSERT INTO Activity_Categories (ActivityID, CategoryID) VALUES
(1, 2), -- 篮球赛 -> 文体娱乐
(2, 1), -- Python讲座 -> 学术讲座
(3, 4); -- 英语角 -> 社团活动 (假设)

-- 活动-主办方关联
INSERT INTO Organizers (ActivityID, InstituteID) VALUES
(1, 1), -- 篮球赛 -> 计算机学院
(2, 1), -- Python讲座 -> 计算机学院
(3, 2); -- 英语角 -> 外国语学院 (假设)

-- 用户-兴趣关联
INSERT INTO User_Interests (UserID, InterestID) VALUES
(1, 1), (1, 3), -- student1 -> 编程, 篮球
(2, 1), (2, 8); -- teacher1 -> 编程, 物理学

-- 报名记录
INSERT INTO Registrations (UserID, ActivityID, Status) VALUES
(1, 1, '已报名'), -- student1 报名了篮球赛
(1, 2, '已报名'); -- student1 报名了Python讲座

-- 反馈记录
INSERT INTO Feedbacks (UserID, ActivityID, Rating, Comment) VALUES
(1, 4, 4, '活动组织得不错，就是时间有点短。'); -- student1 对已结束的活动反馈

-- --- 触发器定义 ---
DELIMITER //

-- 触发器1：检查活动报名容量和状态
CREATE TRIGGER check_activity_capacity_before_insert
BEFORE INSERT ON Registrations
FOR EACH ROW
BEGIN
    DECLARE current_capacity INT;
    DECLARE current_registrations INT;
    DECLARE activity_status ENUM('未开始', '进行中', '已结束', '已取消');

    -- 获取活动详情
    SELECT Capacity, Status INTO current_capacity, activity_status
    FROM Activities
    WHERE ActivityID = NEW.ActivityID;

    -- 检查活动是否开放报名 (理论上只有'未开始'可以报名，但根据需求可调整)
    IF activity_status != '未开始' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = '错误：该活动当前不接受报名 (状态非 "未开始")。';
    END IF;

    -- 如果容量有限制，检查是否已满
    IF current_capacity > 0 THEN
        -- 计算当前 '已报名' 人数
        SELECT COUNT(*) INTO current_registrations
        FROM Registrations
        WHERE ActivityID = NEW.ActivityID AND Status = '已报名';

        -- 检查是否超出容量
        IF current_registrations >= current_capacity THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = '错误：该活动报名人数已满。';
        END IF;
    END IF;
END //

-- 触发器2：检查活动时间地点冲突
CREATE TRIGGER check_activity_time_location_conflict_before_insert
BEFORE INSERT ON Activities
FOR EACH ROW
BEGIN
    DECLARE conflict_count INT;

    -- 检查在同一地点、时间段内是否有其他未取消的活动
    -- 注意：对于线上活动 (LocationID 为 NULL 或特定值)，此检查可能需要调整或跳过
    IF NEW.LocationID IS NOT NULL THEN
        SELECT COUNT(*) INTO conflict_count
        FROM Activities
        WHERE LocationID = NEW.LocationID
          AND ActivityID != NEW.ActivityID -- 排除自身 (虽然是 BEFORE INSERT，但以防万一)
          AND Status != '已取消'
          AND NEW.StartTime < EndTime   -- 新活动开始时间 < 已有活动结束时间
          AND NEW.EndTime > StartTime;  -- 新活动结束时间 > 已有活动开始时间

        IF conflict_count > 0 THEN
            SIGNAL SQLSTATE '45001'
            SET MESSAGE_TEXT = '错误：该时间段内此地点已有其他活动安排。';
        END IF;
    END IF;

    -- 检查时间逻辑 (虽然表有 CHECK，触发器可以提供更友好的错误)
    IF NEW.StartTime >= NEW.EndTime THEN
        SIGNAL SQLSTATE '45002'
        SET MESSAGE_TEXT = '错误：活动开始时间必须早于结束时间。';
    END IF;

    -- 检查 Capacity (如果表结构没有 CHECK 约束)
    IF NEW.Capacity < 0 THEN
         SIGNAL SQLSTATE '45003'
         SET MESSAGE_TEXT = '错误：活动容量不能为负数。';
    END IF;
END //

DELIMITER ;