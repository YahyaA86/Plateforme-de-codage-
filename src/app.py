from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import ollama
from flask_cors import CORS
import subprocess
import os
import tempfile
import threading
import time
import shutil
import markdown
import re
from urllib.parse import unquote
import json

app = Flask(__name__)
CORS(app)

EXECUTION_COMMANDS = {
    'python': ['python', '{filepath}'],
    'javascript': ['node', '{filepath}'],
    'java': ['javac', '{filepath}', '&&', 'java', '{filename}'],
    'c': ['gcc', '{filepath}', '-o', '{output}', '&&', './{output}'],
    'ruby': ['ruby', '{filepath}'],
    'html/css': ['echo', 'HTML/CSS ne peut pas être exécuté de cette façon']
}

LANGUAGE_EXTENSIONS = {
    'python': 'py',
    'javascript': 'js',
    'java': 'java',
    'c': 'c',
    'ruby': 'rb',
    'html/css': 'html'
}

exercise_cache = {}
cache_lock = threading.Lock()

def clean_markdown(content):
    content = re.sub(r'^#+\s*.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'```.*?\n', '', content, flags=re.DOTALL)
    content = re.sub(r'`', '', content)
    return content.strip()

@app.route('/')
def home():
    session.clear()
    return render_template('home.html')

@app.route('/index')
def index():
    session.clear()
    return render_template('index.html')

@app.route('/editor')
def editor():
    try:
        cache_key = request.args.get('cache_key', '')
        if not cache_key or cache_key not in exercise_cache:
            return redirect(url_for('home'))

        exercise_data = exercise_cache[cache_key]
        exercise_md = exercise_data.get('exercise', '')
        language = exercise_data.get('language', 'Python')
        topic = exercise_data.get('topic', 'Programmation')

        exercise_html = markdown.markdown(exercise_md)
        exercise_html = clean_markdown(exercise_html)

        return render_template('editor.html',
                            exercise=exercise_html,
                            language=language,
                            topic=topic,
                            cache_key=cache_key)

    except Exception as e:
        app.logger.error(f"Error in editor route: {str(e)}")
        return redirect(url_for('home'))

@app.route('/generate', methods=['POST'])
def generate_exercise():
    start_time = time.time()
    try:
        data = request.get_json()
        topic = data.get('topic', '').strip()
        language = data.get('language', '').strip()
        cache_key = data.get('cache_key', '').strip()

        if not topic or not language:
            return jsonify({"error": "Topic and language are required"}), 400

        with cache_lock:
            if cache_key and cache_key in exercise_cache:
                return jsonify({
                    **exercise_cache[cache_key],
                    "cached": True,
                    "time": time.time() - start_time
                })

        prompt = f"""
        Crée un exercice de programmation complet en {language} sur le thème: {topic}.
        Fournis une description claire, des consignes précises, 
        un exemple de solution bien commenté entre triple backticks avec le label 'Solution',
        et la sortie attendue. Formatte le tout en markdown.
        """

        response = ollama.chat(
            model="mistral",
            messages=[{"role": "user", "content": prompt}],
            options={'temperature': 0.7, 'timeout': 60}
        )

        exercise_content = response["message"]["content"].strip()
        
        # Extraction de la solution
        solution_match = re.search(r'```.*?\n(.*?)```', exercise_content, re.DOTALL)
        solution = solution_match.group(1).strip() if solution_match else ""
        exercise = re.sub(r'```.*?```', '', exercise_content, flags=re.DOTALL).strip()

        exercise_data = {
            "exercise": exercise,
            "solution": solution,
            "language": language,
            "topic": topic,
            "generated_at": int(time.time())
        }

        with cache_lock:
            cache_key = f"{topic}_{language}_{int(time.time())}".lower().replace(" ", "_")
            exercise_cache[cache_key] = exercise_data
            session['last_exercise'] = exercise_data

        return jsonify({
            **exercise_data,
            "cache_key": cache_key,
            "time": time.time() - start_time
        })

    except Exception as e:
        app.logger.error(f"Generation error: {str(e)}")
        return jsonify({
            "error": f"Erreur lors de la génération: {str(e)}",
            "time": time.time() - start_time
        }), 500

@app.route('/execute', methods=['POST'])
def execute_code():
    try:
        data = request.get_json()
        code = data.get('code', '')
        language = data.get('language', 'python').lower()

        if not code or not language:
            return jsonify({"error": "Code and language are required"}), 400

        ext = LANGUAGE_EXTENSIONS.get(language, 'txt')
        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False, mode='w', encoding='utf-8') as f:
            f.write(code)
            filepath = f.name

        try:
            if language not in EXECUTION_COMMANDS:
                return jsonify({"error": "Langage non supporté"}), 400

            filename = os.path.basename(filepath).split('.')[0]
            commands = EXECUTION_COMMANDS[language].copy()
            
            for i in range(len(commands)):
                commands[i] = commands[i].format(
                    filepath=filepath,
                    filename=filename,
                    output=filename
                )

            if language == 'c':
                output_file = os.path.join(os.path.dirname(filepath), filename)
                commands = ['gcc', filepath, '-o', output_file, '&&', output_file]

            result = subprocess.run(
                ' '.join(commands),
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=15
            )

            output = {
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode
            }

            return jsonify(output)

        finally:
            try:
                os.unlink(filepath)
                if language == 'c' and 'output_file' in locals():
                    os.unlink(output_file)
            except:
                pass

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout: le code a pris trop de temps à s'exécuter"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/validate', methods=['POST'])
def validate_solution():
    try:
        data = request.get_json()
        code = data.get('code', '')
        language = data.get('language', '')
        cache_key = data.get('cache_key', '')

        if not code or not language or not cache_key:
            return jsonify({"error": "Données manquantes"}), 400

        with cache_lock:
            if cache_key not in exercise_cache:
                return jsonify({"error": "Exercice introuvable"}), 404
            
            exercise_data = exercise_cache[cache_key]
            exercise_content = exercise_data['exercise']
            expected_solution = exercise_data['solution']

        # Ask AI to validate the solution
        prompt = f"""
        Voici un exercice de programmation en {language}:
        {exercise_content}

        La solution attendue est:
        ```{language}
        {expected_solution}
        ```

        Un utilisateur a soumis cette solution:
        ```{language}
        {code}
        ```

        Analyse cette solution et réponds avec un JSON contenant:
        - "valid": true/false si la solution est correcte
        - "feedback": une explication détaillée
        - "score": un score de 0 à 100

        La réponse doit être un JSON valide, sans texte supplémentaire.
        """

        response = ollama.chat(
            model="mistral",
            messages=[{"role": "user", "content": prompt}],
            options={'temperature': 0.2, 'timeout': 30},
            format="json"
        )

        try:
            validation_data = response["message"]["content"].strip()
            # Nettoyer la réponse pour extraire uniquement le JSON
            json_start = validation_data.find('{')
            json_end = validation_data.rfind('}') + 1
            clean_json = validation_data[json_start:json_end]
            
            result = json.loads(clean_json)
            return jsonify(result)
        except json.JSONDecodeError:
            return jsonify({
                "valid": False,
                "feedback": "Erreur lors de l'analyse de la solution",
                "score": 0
            })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "valid": False,
            "feedback": "Erreur lors de la validation",
            "score": 0
        }), 500

@app.route('/get-solution')
def get_solution():
    cache_key = request.args.get('cache_key')
    if not cache_key:
        return jsonify({"error": "Cache key required"}), 400
    with cache_lock:
        if cache_key not in exercise_cache:
            return jsonify({"error": "Solution non trouvée"}), 404
        solution = exercise_cache[cache_key].get("solution", "")
        return jsonify({"solution": solution})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
