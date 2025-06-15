# Fil: create_item_list.py
import csv
import json

INPUT_CSV_FILE = 'invTypes.csv'
OUTPUT_JSON_FILE = 'items.json'

def create_market_item_list():
    """
    Leser den store invTypes.csv-filen og lager en ren items.json
    som kun inneholder publiserte markedsvarer.
    """
    market_items = {}
    print(f"Leser fra {INPUT_CSV_FILE}...")
    
    try:
        with open(INPUT_CSV_FILE, mode='r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                # Vi vil kun ha varer som er publisert på markedet.
                # 'published' er 1 for ja, 0 for nei.
                if row.get('published') == '1' and row.get('marketGroupID'):
                    type_id = int(row['typeID'])
                    type_name = row['typeName']
                    market_items[type_name] = type_id
        
        print(f"Fant {len(market_items)} gjenstander som kan handles på markedet.")

        with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as outfile:
            json.dump(market_items, outfile, indent=4, ensure_ascii=False)
            
        print(f"Vellykket! Den komplette listen er lagret i {OUTPUT_JSON_FILE}")
        print("Du kan nå slette den store invTypes.csv-filen hvis du vil.")

    except FileNotFoundError:
        print(f"FEIL: Kunne ikke finne filen '{INPUT_CSV_FILE}'.")
        print("Sørg for at du har lastet ned og pakket ut filen i samme mappe som dette scriptet.")
    except Exception as e:
        print(f"En uventet feil oppstod: {e}")

if __name__ == '__main__':
    create_market_item_list()