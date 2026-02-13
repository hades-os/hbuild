from pymysql import Connection, cursors

class HBuildLog():
    @staticmethod
    def insert_log(conn: Connection, package: str, stage: str, log: str):
        with conn.cursor() as cursor:
            sql = "INSERT INTO `sql`.`logs` (`package`, `stage`, `log`) VALUES (%s, %s, %s)"
            cursor.execute(sql, (package, stage, log))
            conn.commit()

    @staticmethod
    def select_logs(conn: Connection, package: str, stage: str):
        with conn.cursor() as cursor:
            if stage is not None:
                sql = "SELECT * FROM `sql`.`logs` WHERE `package` = %s AND `stage` = %s"
                cursor.execute(sql, (package, stage))
            else:
                sql = "SELECT * FROM `sql`.`logs` WHERE `package` = %s"
                cursor.execute(sql, package)
            return cursor.fetchall()

    @staticmethod
    def insert_history(conn: Connection, runner: str, packages: list[str]):
        with conn.cursor() as cursor:
            sql = "INSERT INTO `sql`.`history` (`runner`, `packages`) VALUES (%s, %s)"
            packages_csq = ",".join(packages)
            cursor.execute(sql, (runner, packages_csq))
            conn.commit()

    @staticmethod
    def select_history(conn: Connection):
        with conn.cursor() as cursor:
            sql = "SELECT * FROM `sql`.`history`"
            cursor.execute(sql)
            return cursor.fetchall()