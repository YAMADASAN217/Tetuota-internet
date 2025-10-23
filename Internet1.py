import socket
import html.parser
import tkinter as tk
from tkinter import scrolledtext
from urllib.parse import urlparse, urljoin
import ssl 
from socket import gaierror, timeout, error as socket_error 
from ssl import SSLError

# --- 1. HTTP/HTTPS通信部分（socket + sslを使用） ---
def get_html_content(url):
    """
    指定されたURL (HTTP/HTTPS) から生のHTMLコンテンツをソケット通信で取得します。
    """
    parsed_url = urlparse(url)
    host = parsed_url.netloc
    path = parsed_url.path if parsed_url.path else "/"
    scheme = parsed_url.scheme
    
    # スキームに応じてポートとSSLコンテキストを設定
    if scheme == "https":
        port = 443
        use_ssl = True
    elif scheme == "http":
        port = 80
        use_ssl = False
    else:
        return f"Error: 未対応のプロトコル ({scheme}) です。httpまたはhttpsを使用してください。"

    if not host:
        return "Error: 無効なURL形式です。ホスト名が含まれていません。"
        
    sock = None
    try:
        # 1. TCPソケットを作成し、接続
        sock = socket.create_connection((host, port), timeout=5)
        
        # 2. HTTPSの場合、ソケットをSSLでラップ
        if use_ssl:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)

        # 3. HTTP GETリクエストを作成し送信
        request = (
            f"GET {path} HTTP/1.0\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: SimplePythonBrowser/1.0\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        sock.sendall(request.encode('utf-8'))

        # 4. レスポンスを受信
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk

        # レスポンスヘッダーとボディを分離
        response_text = response.decode('utf-8', errors='ignore')
        header_end = response_text.find("\r\n\r\n")
        
        if header_end == -1:
            return "Error: 無効なHTTPレスポンス形式です。"

        # HTTPステータスコードの確認
        status_line = response_text.split('\r\n')[0]
        if not status_line.startswith("HTTP/1.") or " 200 " not in status_line:
             return f"Error: HTTPステータスコードエラー\n\n--- レスポンスヘッダー --- \n{response_text[:header_end]}"
             
        return response_text[header_end + 4:]

    except gaierror:
        return f"Error: ホスト名 ({host}) の解決に失敗しました。"
    except timeout:
        return "Error: 接続またはデータ受信がタイムアウトしました。"
    except socket_error as e:
        return f"Error: ソケット通信中にエラーが発生しました。\n詳細: {e}"
    except SSLError as e:
        return f"Error: SSL/TLSエラーが発生しました。\n詳細: {e}"
    except Exception as e:
        return f"Error: 予期せぬエラーが発生し、通信が中断されました。\n詳細: {e}"
    finally:
        if sock:
            sock.close()


# --- 2. HTML解析部分（html.parserを使用） ---
class HyperlinkParser(html.parser.HTMLParser):
    """HTMLを解析し、Textウィジェットに出力し、リンクを処理するパーサー。"""
    def __init__(self, output_text_widget, base_url, load_command):
        super().__init__()
        self.output_widget = output_text_widget
        self.base_url = base_url
        self.load_command = load_command
        self.in_body = False
        self.in_link = False
        self.link_url = ""
        
        # --- 修正箇所 1: 無視すべきタグのネストを追跡するためのカウンター ---
        self.ignore_depth = 0 
        self.ignore_tags = ('script', 'style', 'head', 'title', 'meta')

        self.output_widget.tag_config("link", foreground="blue", underline=1)
        
    def _handle_link_click(self, event):
        """リンククリック時の処理"""
        index = self.output_widget.index("@%s,%s" % (event.x, event.y))
        
        for tag in self.output_widget.tag_names(index):
            if tag.startswith("link_"):
                target_url = tag[5:] 
                self.load_command(target_url)
                break

    def handle_starttag(self, tag, attrs):
        if tag == 'body':
            self.in_body = True
        
        # --- 修正箇所 2: 無視すべきタグの開始時にカウンターを増やす ---
        if tag in self.ignore_tags:
            self.ignore_depth += 1

        elif tag == 'a':
            self.in_link = True
            self.link_url = ""
            attrs_dict = dict(attrs)
            href = attrs_dict.get('href')
            if href:
                self.link_url = urljoin(self.base_url, href)

        elif tag in ('p', 'div', 'br', 'h1', 'h2', 'h3') and self.in_body and self.ignore_depth == 0:
            self.output_widget.insert(tk.END, '\n\n')

    def handle_endtag(self, tag):
        if tag == 'body':
            self.in_body = False
        
        # --- 修正箇所 3: 無視すべきタグの終了時にカウンターを減らす ---
        if tag in self.ignore_tags and self.ignore_depth > 0:
            self.ignore_depth -= 1

        elif tag == 'a':
            self.in_link = False
            self.link_url = ""
        
        elif tag in ('p', 'div') and self.in_body and self.ignore_depth == 0:
            self.output_widget.insert(tk.END, '\n\n')


    def handle_data(self, data):
        # --- 修正箇所 4: current_tagではなく、ignore_depthで判定 ---
        if self.in_body and self.ignore_depth == 0:
            cleaned_data = ' '.join(data.split())
            if not cleaned_data:
                return

            if self.in_link and self.link_url:
                tag_name_url = f"link_{self.link_url}"
                self.output_widget.tag_bind(tag_name_url, "<Button-1>", self._handle_link_click)
                self.output_widget.insert(tk.END, cleaned_data + ' ', ("link", tag_name_url))
            else:
                self.output_widget.insert(tk.END, cleaned_data + ' ')

    def error(self, message):
        pass

# --- 3. GUIとメインロジック部分（tkinterを使用） ---
class FullBrowserApp:
    def __init__(self, master):
        self.master = master
        master.title("鉄オタインターネット (HTTPS対応・修正済み)") 

        top_frame = tk.Frame(master)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.url_entry = tk.Entry(top_frame, width=70)
        self.url_entry.insert(0, "https://example.com") 
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.go_button = tk.Button(top_frame, text="Go", command=lambda: self.load_page(self.url_entry.get()))
        self.go_button.pack(side=tk.RIGHT, padx=5)

        self.text_area = scrolledtext.ScrolledText(master, wrap=tk.WORD, width=80, height=30, font=('Helvetica', 12))
        self.text_area.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        self.text_area.config(state=tk.DISABLED)

        self.text_area.config(state=tk.NORMAL)
        self.text_area.insert(tk.END, "URLを入力してGoボタンを押してください（HTTPとHTTPSに対応）。")
        self.text_area.config(state=tk.DISABLED)


    def load_page(self, url):
        """指定されたURLのページを読み込むメイン処理"""
        
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, url)
        
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete(1.0, tk.END)
        self.text_area.insert(tk.END, f"接続中: {url}...\n\n", "status")
        self.text_area.update_idletasks() # UIの強制更新

        html_content = get_html_content(url)
        
        self.text_area.delete(1.0, tk.END)
        
        if html_content.startswith("Error:"):
            self.text_area.tag_config("error", foreground="red")
            self.text_area.insert(tk.END, html_content, "error")
        else:
            parser = HyperlinkParser(self.text_area, url, self.load_page)
            
            try:
                parser.feed(html_content)
            except Exception as e:
                self.text_area.tag_config("error", foreground="red")
                self.text_area.insert(tk.END, f"致命的なパースエラー:\n{e}", "error")
            finally:
                parser.close()

        self.text_area.config(state=tk.DISABLED)

# アプリの実行
if __name__ == "__main__":
    root = tk.Tk()
    app = FullBrowserApp(root)
    root.mainloop()
