import socket
# ... (他のimportはそのまま)
import re
import zlib 

# ... (USER_AGENTとget_html_content関数は変更なし)

# --- 新規関数：文字クリーンアップシステム ---
def clean_html_data(html_content):
    """
    Tkinterでの表示エラーを防ぐため、HTMLコンテンツから制御文字や
    特殊なUnicode文字を取り除き、クリーンなASCII文字と改行・空白のみにする。
    """
    if not isinstance(html_content, str):
        return ""
        
    # 1. 見た目を乱す連続する改行を一つにまとめる
    content = re.sub(r'\n{3,}', '\n\n', html_content)
    
    # 2. Tkinterが嫌がる制御文字や特殊記号を全て削除
    # \x00-\x1F (制御文字), \x7F (DEL), \uFFFD (デコードエラーの代替文字) などを削除
    cleaned_content = "".join(char for char in content if char.isprintable() or char.isspace())
    
    # 念のため、HTMLエンティティ（&nbsp;など）を一時的に空白に戻す
    cleaned_content = cleaned_content.replace('&nbsp;', ' ')
    
    return cleaned_content


# --- 2. HTML解析部分（HyperlinkParserは変更なし） ---
class HyperlinkParser(html.parser.HTMLParser):
    # ... (クラス定義は変更なし)
    # ...
    
# --- 3. GUIとメインロジック部分（tkinterを使用） ---
class FullBrowserApp:
    # ... (__init__は変更なし)
    # ...

    def load_page(self, url):
        """指定されたURLのページを読み込むメイン処理"""
        
        # ... (接続・エラー処理は変更なし)
        
        if html_content.startswith("Error:"):
            # ... (エラー表示処理は変更なし)
        else:
            # ★★★ 修正箇所：HTMLコンテンツをクリーンアップ ★★★
            cleaned_html = clean_html_data(html_content)
            
            parser = HyperlinkParser(self.text_area, final_url, self.load_page)
            
            try:
                # クリーンアップされたデータをパース
                parser.feed(cleaned_html) 
            except Exception as e:
                self.text_area.tag_config("error", foreground="red")
                self.text_area.insert(tk.END, f"致命的なパースエラー:\n{e}", "error")
            finally:
                parser.close()

        self.text_area.config(state=tk.DISABLED)

# ... (アプリの実行は変更なし)
