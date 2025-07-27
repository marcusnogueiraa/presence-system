import requests
import time

# ===== CONFIGURAÇÕES =====
BASE_URL = "http://localhost:5000"  # URL do servidor Flask
TURMA_ID = "3b2f1293-86e0-45f1-a337-5bc41f2ee878"  # UUID da turma

# Lista de alunos para cadastrar (nome, matrícula, RFID)
ALUNOS = [
    {"nome": "João Silva", "matricula": "2023001", "rfid": "RFID001"},
    {"nome": "Maria Oliveira", "matricula": "2023002", "rfid": "RFID002"},
    {"nome": "Carlos Souza", "matricula": "2023003", "rfid": "RFID003"},
    {"nome": "Ana Costa", "matricula": "2023004", "rfid": "RFID004"},
    {"nome": "Pedro Alves", "matricula": "2023005", "rfid": "RFID005"},
]

# ===== FUNÇÃO PARA ADICIONAR ALUNO =====
def adicionar_aluno(nome, matricula, rfid):
    """Adiciona um aluno ao sistema"""
    url = f"{BASE_URL}/adicionar_aluno"
    dados = {
        'turma_id': TURMA_ID,
        'nome': nome,
        'matricula': matricula,
        'rfid': rfid
    }
    
    try:
        response = requests.post(url, data=dados, allow_redirects=False)
        
        # Verifica se houve redirecionamento com erro
        if 300 <= response.status_code < 400:
            location = response.headers.get('Location', '')
            if 'error=' in location:
                error_msg = location.split('error=')[1]
                return f"ERRO: {error_msg}"
            return "Sucesso (redirecionado)"
        
        # Verifica resposta direta
        if response.status_code == 200:
            return "Sucesso"
            
        return f"Erro HTTP: {response.status_code}"
        
    except Exception as e:
        return f"Erro conexão: {str(e)}"

# ===== EXECUÇÃO PRINCIPAL =====
if __name__ == "__main__":
    print("=" * 60)
    print(f"CADASTRANDO ALUNOS NA TURMA {TURMA_ID}")
    print("=" * 60)
    
    total = len(ALUNOS)
    sucessos = 0
    falhas = 0
    
    for i, aluno in enumerate(ALUNOS, 1):
        print(f"\n[{i}/{total}] Adicionando {aluno['nome']}...")
        
        resultado = adicionar_aluno(
            aluno['nome'],
            aluno['matricula'],
            aluno['rfid']
        )
        
        if "Sucesso" in resultado or "redirecionado" in resultado:
            print(f"✅ {resultado}")
            sucessos += 1
        else:
            print(f"❌ {resultado}")
            falhas += 1
        
        # Pequeno delay para não sobrecarregar o servidor
        time.sleep(0.5)
    
    print("\n" + "=" * 30)
    print("RESUMO DA OPERAÇÃO:")
    print(f"Alunos processados: {total}")
    print(f"Sucessos: {sucessos}")
    print(f"Falhas: {falhas}")
    print("=" * 30)