from pymysql import Connection, cursors

class HBuildLog():
    @staticmethod
    def insert_log(conn: Connection, package: str, stage: str, log: str):
        with conn.cursor() as cursor:
            sql = "INSERT INTO `sql`.`log` (`package`, `stage`, `log`) VALUES (%s, %s, %s)"
            cursor.execute(sql, (package, stage, log))

    @staticmethod
    def select_logs(conn: Connection, package: str, stage: str):
        with conn.cursor() as cursor:
            sql = "SELECT FROM `sql`.`log` WHERE `package` = %s AND `stage` = %s"
            cursor.execute(sql, (package, stage))
            return cursor.fetchall()