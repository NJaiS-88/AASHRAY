import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

r = [json.loads(l) for l in open('runs.jsonl', encoding='utf-8') if json.loads(l)['scenario_id'] == 'SCEN-DIS-04' and json.loads(l)['pipeline'] == 'jev_llm'][0]
print("SCENARIO:", r['final_json'].get('scenario'))
print("RESOURCES:", [x['resource'] for x in r['final_json']['resources']])
for res in r['final_json']['resources']:
    print("--- RESOURCE:", res['resource'])
    print("INSTRUCTIONS:", res['instructions'])
print("\nRETRIEVED CHUNKS:")
for i, c in enumerate(r['retrieved_chunks']):
    print(f"Chunk {i+1} ({c.get('source_file')}, p{c.get('page')}):")
    print(c.get('chunk_text')[:200] + "...\n")
