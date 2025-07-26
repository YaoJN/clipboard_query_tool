import tkinter as tk
from tkinter import ttk
import threading
import time
import pyperclip
import sqlite3

DB_PATH = r'C:\DB\disk_info.db'  # 数据库路径

class ClipboardSearcher:
    def __init__(self, root):
        self.root = root
        self.root.title("剪贴板查询工具")
        self.root.geometry("600x200")

        self.root.withdraw()  # 启动时隐藏主窗口，不显示Text窗口

        self.last_text = pyperclip.paste()
        self.running = True
        self.result_window = None
        self.tree = None
        self.highlighted_cell = None  # 记录高亮的 (item_id, column_id)

        threading.Thread(target=self.monitor_clipboard, daemon=True).start()

    def monitor_clipboard(self):
        while self.running:
            try:
                current_text = pyperclip.paste()
                if current_text != self.last_text and current_text.strip():
                    self.last_text = current_text
                    result = self.search_database(current_text.strip())
                    self.display_result(result)
            except Exception as e:
                self.display_result([(f"错误：{e}",)])
            time.sleep(1)

    def search_database(self, keyword):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            # 查询 resource_data 表
            cursor.execute(
                "SELECT disk_no, category2, file_path, file_name, file_size, file_created_time, is_deleted "
                "FROM resource_data WHERE file_name LIKE ?", (f"%{keyword}%",))
            resource_data_rows = cursor.fetchall()

            # 查询 rg_4k_files 表
            cursor.execute(
                "SELECT file_name, file_size, file_link FROM rg_4k_files WHERE file_name LIKE ?", (f"%{keyword}%",))
            rg_4k_files_rows = cursor.fetchall()

            # 对 rg_4k_files 的数据对齐成统一列格式（8列）
            aligned_rg_4k_files = []
            for file_name, file_size, file_link in rg_4k_files_rows:
                aligned_rg_4k_files.append((
                    "",       # disk_no 空
                    "",       # category2 空
                    "",       # file_path 空
                    file_name,
                    file_size,
                    "",       # file_created_time 空
                    "",       # is_deleted 空
                    file_link
                ))

            # resource_data 没有 file_link 字段，补空字符串
            aligned_resource_data = []
            for row in resource_data_rows:
                aligned_resource_data.append(row + ("",))

            combined = aligned_resource_data + aligned_rg_4k_files
            return combined
        except Exception as e:
            return [(f"查询出错：{e}",)]
        finally:
            conn.close()

    def get_all_columns(self):
        # 统一的列名，展示所有字段
        return ["disk_no", "category2", "file_path", "file_name", "file_size", "file_created_time", "is_deleted", "file_link"]

    def display_result(self, data):
        if not self.result_window or not self.result_window.winfo_exists():
            self.result_window = tk.Toplevel(self.root)
            self.result_window.title("查询结果")
            self.result_window.geometry("1200x200")
            self.result_window.attributes("-topmost", True)

            self.tree = ttk.Treeview(self.result_window, columns=self.get_all_columns(), show='headings')
            self.tree.pack(expand=True, fill='both')

            column_widths = {
                "disk_no": 50,
                "category2": 80,
                "file_path": 150,
                "file_name": 250,
                "file_size": 80,
                "file_created_time": 150,
                "is_deleted": 60,
                "file_link": 300,
            }

            for col in self.get_all_columns():
                self.tree.heading(col, text=col)
                w = column_widths.get(col, 120)
                self.tree.column(col, width=w, anchor='w')

            # 绑定双击事件，用于切换 is_deleted
            self.tree.bind("<Double-1>", self.on_tree_double_click)

            # 设置各种tag颜色
            self.tree.tag_configure('contains_4k', background='#cce6ff')  # 浅蓝色
            self.tree.tag_configure('empty_category2', background='#ccffcc')  # 浅绿色
            self.tree.tag_configure('contains_mosaic', background='#ffe5cc')  # 浅橙色
            self.tree.tag_configure('contains_av', background='#e5ccff')  # 浅紫色
            self.tree.tag_configure('contains_ido', background='#ffffcc')  # 浅黄色

            self.result_window.protocol("WM_DELETE_WINDOW", self.on_result_window_close)
        else:
            self.tree.delete(*self.tree.get_children())

            # 取消之前高亮
            if self.highlighted_cell:
                item, _ = self.highlighted_cell
                if self.tree.exists(item):
                    self.tree.item(item, tags=())
                self.highlighted_cell = None
        flg_4k = 0
        # 插入数据并给行打标签
        for row in data:
            tags = []

            category2 = str(row[1]).upper() if row[1] else ''

            if '4K' in category2:
                flg_4k = 1
                tags.append('contains_4k')
            elif 'MOSAIC' in category2:
                tags.append('contains_mosaic')
            elif 'AV' in category2:
                tags.append('contains_av')
            elif 'IDOL' in category2 or 'REBD' in category2:
                tags.append('contains_ido')
            else:
                # 只有不存在4k资源时，才为他加高亮
                if not flg_4k:
                    tags.append('empty_category2')

            # is_deleted列如果是 '1' 也加原来黄色高亮
            if len(row) >= 7 and row[6] == '1':
                tags.append('highlight')

            self.tree.insert('', tk.END, values=row, tags=tags)

        self.result_window.deiconify()
        self.result_window.lift()
        self.result_window.focus_force()

    def _highlight_deleted_rows(self):
        # 遍历所有行，is_deleted = '1' 则高亮
        for item in self.tree.get_children():
            vals = self.tree.item(item, 'values')
            if len(vals) >= 7 and vals[6] == '1':
                self.tree.item(item, tags=('highlight',))

    def on_tree_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not row_id or not column:
            return

        col_index = int(column[1:]) - 1
        columns = self.get_all_columns()
        if col_index >= len(columns):
            return

        clicked_column = columns[col_index]

        # 只有点击 is_deleted 列才触发切换更新
        if clicked_column != "is_deleted":
            return

        values = self.tree.item(row_id, "values")
        # 只有 resource_data 表的行有 disk_no，file_name，才可更新
        disk_no = values[0]
        file_name = values[3]
        if not disk_no or not file_name:
            return  # rg_4k_files 表无此字段，跳过

        current_val = values[col_index]
        if current_val not in ('0', '1'):
            return

        new_val = '1' if current_val == '0' else '0'

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE resource_data SET is_deleted = ? WHERE disk_no = ? AND file_name = ?",
                (new_val, disk_no, file_name)
            )
            conn.commit()
        except Exception as e:
            self.display_result([(f"更新数据库失败: {e}",)])
            return
        finally:
            conn.close()

        # 更新表格显示
        new_values = list(values)
        new_values[col_index] = new_val
        self.tree.item(row_id, values=new_values)

        # 更新高亮状态
        if new_val == '1':
            if self.highlighted_cell:
                old_item, _ = self.highlighted_cell
                if self.tree.exists(old_item):
                    self.tree.item(old_item, tags=())
            self.tree.item(row_id, tags=('highlight',))
            self.highlighted_cell = (row_id, column)
        else:
            self.tree.item(row_id, tags=())
            if self.highlighted_cell and self.highlighted_cell[0] == row_id:
                self.highlighted_cell = None

    def on_result_window_close(self):
        self.running = False
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = ClipboardSearcher(root)
    root.mainloop()
