import os
import sys
from core.ai_service import KairosAIService
from core.db import get_engine
from core.models import StoreProduct
from sqlalchemy.orm import Session
from domain.meal_planner import generate_real_meal_plan

def test():
    print("--- DIAGNÓSTICO KAIROS v5.13 ---")
    svc = KairosAIService()
    
    # 1. Get AI / Local Response
    ai_resp = svc.get_chat_response([{'role': 'user', 'content': 'tengo 25 lucas'}], {'budget': None})
    print(f"REPLY: {ai_resp.get('reply')}")
    
    if not ai_resp.get('meal_plan'):
        print("[ERROR] AI no generó menú.")
        return

    # 2. Map to Real Products (The part that was showing $0)
    engine = get_engine()
    with Session(engine) as s:
        real_plans = generate_real_meal_plan(s, ai_resp['meal_plan'])
        
        for plan in real_plans:
            print(f"\nPLAN: {plan['title']}")
            print(f"TOTAL ESTIMADO: ${plan['total_cost']:,}")
            print(f"TIENDAS: {', '.join(plan['stores_visited'])}")
            
            for item in plan['items']:
                status = item.get('status', 'not_found')
                if status == 'optimized':
                    print(f"  [OK] {item['name']} - ${item['price']:,} ({item['store']})")
                else:
                    print(f"  [X] No se encontró: {item.get('query')}")

if __name__ == "__main__":
    # Ensure backend path is in sys.path
    backend_path = os.path.dirname(os.path.abspath(__file__))
    if backend_path not in sys.path:
        sys.path.append(backend_path)
    test()
