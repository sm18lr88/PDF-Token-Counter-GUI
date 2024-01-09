import os
import PySimpleGUI as sg
import tiktoken
import fitz
import threading
import queue

stop_event = threading.Event()
pause_event = threading.Event()

def count_tokens_from_pdf(pdf_path, enc):
    try:
        with fitz.open(pdf_path) as doc:
            text = "".join(page.get_text() for page in doc)
        return len(enc.encode(text))
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return 0

def process_pdf_files(pdf_files, enc, progress_queue):
    processed_files = 0
    total_tokens = 0
    for pdf in pdf_files:
        if stop_event.is_set():
            progress_queue.put(('STOPPED', total_tokens, processed_files))
            return
        while pause_event.is_set():
            if stop_event.is_set():
                progress_queue.put(('STOPPED', total_tokens, processed_files))
                return
        total_tokens += count_tokens_from_pdf(pdf, enc)
        processed_files += 1
        progress_queue.put(('PROGRESS', total_tokens, processed_files))
    progress_queue.put(('COMPLETE', total_tokens, processed_files))

def calculate_cost(token_count):
    return (token_count / 1000) * 0.01 # gpt-4-110-preview price per input of 1k tokens is $0.01.

def create_window():
    sg.theme('BlueMono')
    layout = [
        [sg.Text('Select folder with PDFs:'), sg.InputText(key='-FOLDER-'), sg.FolderBrowse()],
        [sg.Text('Estimated cost is based on gpt-4-1106-preview model pricing.')],
        [sg.Button('Count Tokens', key='-COUNT-'), sg.Button('Pause', key='-PAUSE-'), sg.Button('Stop', key='-STOP-')],
        [sg.Text('Total token count:', size=(40, 1), key='-TOKENS-')],
        [sg.Text('Estimated cost:', size=(40, 1), key='-COST-')],
        [sg.ProgressBar(100, orientation='h', size=(20, 20), key='-PROGRESSBAR-')]
    ]
    return sg.Window('Token Counter', layout, finalize=True)

def main():
    window = create_window()
    encoding = "cl100k_base"
    enc = tiktoken.get_encoding(encoding)
    progress_queue = queue.Queue()

    while True:
        event, values = window.read(timeout=100)
        if event == sg.WIN_CLOSED or event == '-STOP-':
            stop_event.set()
            break
        if event == '-COUNT-':
            stop_event.clear()
            pause_event.clear()
            window['-STOP-'].update(disabled=False)
            window['-PAUSE-'].update('Pause')
            window['-PROGRESSBAR-'].update_bar(0)
            folder_path = values['-FOLDER-']
            pdf_files = [os.path.join(root, f) for root, dirs, files in os.walk(folder_path) for f in files if f.lower().endswith('.pdf')]
            total_files = len(pdf_files) #Progress bar works based on total # of PDF files detected in folder.
            window['-TOKENS-'].update('Total token count: 0')
            window['-COST-'].update('Estimated cost: $0.00')
            threading.Thread(target=process_pdf_files, args=(pdf_files, enc, progress_queue), daemon=True).start()
        if event == '-PAUSE-':
            pause_event.set() if not pause_event.is_set() else pause_event.clear()
            window['-PAUSE-'].update('Resume' if pause_event.is_set() else 'Pause')

        try:
            message_type, total_tokens, processed_files = progress_queue.get_nowait()
            if message_type in ('PROGRESS', 'STOPPED', 'COMPLETE'):
                if message_type == 'COMPLETE':
                    window['-PROGRESSBAR-'].update_bar(100)
                else:
                    progress_percentage = (processed_files / total_files) * 100
                    window['-PROGRESSBAR-'].update_bar(progress_percentage)
                formatted_token_count = f"{total_tokens:,}"
                cost_estimate = calculate_cost(total_tokens)
                formatted_cost_estimate = f"${cost_estimate:,.2f}"
                window['-TOKENS-'].update(f'Total token count: {formatted_token_count}')
                window['-COST-'].update(f'Estimated cost: {formatted_cost_estimate}')
                if message_type == 'STOPPED':
                    sg.popup('Token counting stopped.')
                    window['-STOP-'].update(disabled=False)
        except queue.Empty:
            pass

    window.close()

if __name__ == '__main__':
    main()
