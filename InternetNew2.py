import socket
import html.parser
import tkinter as tk
from tkinter import scrolledtext
from urllib.parse import urlparse, urljoin
import ssl 
from socket import gaierror, timeout, error as socket_error 
from ssl import SSLError
import re
import zlib # Gzip圧縮解凍用

# User-Agentを一般的なブラウザに偽装してブロックを回避
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.88 Safari/537.36"

# --- 1. HTTP/HTTPS通信部分（socket + ssl + リダイレクト + GZIP解凍） ---
def get_html_content(url, redirect_count=0):
    """
    リダイレクト、User-Agent偽装、Gzip圧縮解凍に対応したHTML取得関数。
    """
    if redirect_count >= 5:
        return "Error: リダイレクトが多すぎます（無限ループの可能性があります）。", url
        
    parsed_url = urlparse(url)
    host = parsed_url.netloc
    path = parsed_url.path if parsed_url.path else "/"
    scheme = parsed_url.scheme
    
    if not scheme and host:
        return get_html_content(f"https://{url}", redirect_count)
    
    if scheme == "https":
        port = 443
        use_ssl = True
    elif scheme == "http":
        port = 80
        use_ssl = False
    else:
        return f"Error: 未対応のプロトコル ({scheme}) です。", url

    if not host:
        return "Error: 無効なURL形式です。ホスト名が含まれていません。", url
        
    sock = None
    try:
        # TCPソケットを作成し、接続 (タイムアウト15秒)
        sock = socket.create_connection((host, port), timeout=15) 
        
        # HTTPSの場合、ソケットをSSLでラップ
        if use_ssl:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)

        # HTTP GETリクエストを作成し送信 (Gzip対応を要求)
        request = (
            f"GET {path} HTTP/1.0\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {USER_AGENT}\r\n"
            f"Accept-Encoding: gzip, deflate\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        sock.sendall(request.encode('utf-8'))

        # レスポンスを受信
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk

        # ヘッダーとボディの分離
        header_body_split = response.find(b"\r\n\r\n")
        if header_body_split == -1:
            return "Error: 無効なHTTPレスポンス形式です。", url
            
        header_bytes = response[:header_body_split]
        body_bytes = response[header_body_split + 4:]
        header_text = header_bytes.decode('utf-8', errors='ignore')

        # ステータスコードの解析
        status_line = header_text.split('\r\n')[0]
        try:
            status_code = int(status_line.split()[1])
        except (IndexError, ValueError):
            return "Error: 無効なHTTPステータスラインです。", url

        # --- リダイレクト処理 (300-399) ---
        if 300 <= status_code < 400:
            location_match = re.search(r"Location:\s*(.*)\r\n", header_text, re.IGNORECASE)
            
            if location_match:
                new_url_relative = location_match.group(1).strip()
                new_url = urljoin(url, new_url_relative)
                return get_html_content(new_url, redirect_count + 1)
            else:
                return f"Error: リダイレクト ({status_code}) ですが、Locationヘッダーが見つかりませんでした。", url
        
        # 200 OK以外はエラーとして表示
        if status_code != 200:
             return f"Error: HTTPステータスコードエラー ({status_code})\n\n--- レスポンスヘッダー --- \n{header_text}", url
        
        # --- 圧縮データの解凍処理 ---
        if re.search(r"Content-Encoding:\s*gzip", header_text, re.IGNORECASE):
            try:
                # Gzip解凍。wbits=16|zlib.MAX_WBITSでGzipヘッダー付きに対応
                html_content = zlib.decompress(body_bytes, 16 + zlib.MAX_WBITS).decode('utf-8', errors='ignore')
            except zlib.error as e:
                return f"Error: Gzip解凍エラーが発生しました。\n詳細: {e}", url
        else:
            # 圧縮されていない場合はそのままデコード
            html_content = body_bytes.decode('utf-8', errors='ignore')
             
        # 成功
        return html_content, url

    except gaierror:
        return f"Error: ホスト名 ({host}) の解決に失敗しました。", url
    except timeout:
        return "Error: 接続またはデータ受信がタイムアウトしました。", url
    except socket_error as e:
        return f"Error: ソケット通信中にエラーが発生しました。\n詳細: {e}", url
    except SSLError as e:
        return f"Error: SSL/TLSエラーが発生しました。\n詳細: {e}", url
    except Exception as e:
        return f"Error: 予期せぬエラーが発生し、通信が中断されました。\n詳細: {e}", url
    finally:
        if sock:
            sock.close()


# --- 2. HTML解析部分（html.parserを使用） ---
class HyperlinkParser(html.parser.HTMLParser):
    """
    全テキスト表示とリンク処理を統合したパーサー。
    'current_tag'バグを完全に排除したクリーンバージョン。
    """
    def __init__(self, output_text_widget, base_url, load_command):
        super().__init__()
        self.output_widget = output_text_widget
        self.base_url = base_url
        self.load_command = load_command
        self.in_link = False
        self.link_url = ""
        # スクリプトなどを無視するための深さカウンター
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
        # 無視タグの深さをインクリメント
        if tag in self.ignore_tags:
            self.ignore_depth += 1

        elif tag == 'a':
            self.in_link = True
            self.link_url = ""
            attrs_dict = dict(attrs)
            href = attrs_dict.get('href')
            if href:
                self.link_url = urljoin(self.base_url, href)

        # 無視タグの中にいない場合のみ改行
        # ここに 'self.current_tag' のような参照は一切ありません
        elif tag in ('p', 'div', 'br', 'h1', 'h2', 'h3') and self.ignore_depth == 0:
            self.output_widget.insert(tk.END, '\n\n')

    def handle_endtag(self, tag):
        # 無視タグの深さをデクリメント
        if tag in self.ignore_tags and self.ignore_depth > 0:
            self.ignore_depth -= 1

        elif tag == 'a':
            self.in_link = False
            self.link_url = ""
        
        # 無視タグの中にいない場合のみ改行
        elif tag in ('p', 'div') and self.ignore_depth == 0:
            self.output_widget.insert(tk.END, '\n\n')


    def handle_data(self, data):
        # 無視タグの中にいない場合のみデータ処理
        if self.ignore_depth == 0: 
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
        master.title("鉄オタインターネット (真の最終決定版)") 

        top_frame = tk.Frame(master)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.url_entry = tk.Entry(top_frame, width=70)
        self.url_entry.insert(0, "https://www.google.com/") 
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.go_button = tk.Button(top_frame, text="Go", command=lambda: self.load_page(self.url_entry.get()))
        self.go_button.pack(side=tk.RIGHT, padx=5)

        self.text_area = scrolledtext.ScrolledText(master, wrap=tk.WORD, width=80, height=30, font=('Helvetica', 12))
        self.text_area.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        self.text_area.config(state=tk.DISABLED)

        self.text_area.config(state=tk.NORMAL)
        self.text_area.insert(tk.END, "致命的なパースエラーを修正しました！このコードをPythonで実行してください。")
        self.text_area.config(state=tk.DISABLED)


    def load_page(self, url):
        """指定されたURLのページを読み込むメイン処理"""
        
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete(1.0, tk.END)
        self.text_area.insert(tk.END, f"接続中: {url}...\n\n", "status")
        self.text_area.update_idletasks()

        result_tuple = get_html_content(url)
        
        if isinstance(result_tuple, tuple) and len(result_tuple) == 2:
            html_content, final_url = result_tuple
        else:
            html_content = str(result_tuple)
            final_url = url 

        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, final_url)
        
        self.text_area.delete(1.0, tk.END)
        
        if html_content.startswith("Error:"):
            self.text_area.tag_config("error", foreground="red")
            self.text_area.insert(tk.END, html_content, "error")
        else:
            parser = HyperlinkParser(self.text_area, final_url, self.load_page)
            
            try:
                # ここで 'current_tag' エラーが出ないかを確認する！
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
