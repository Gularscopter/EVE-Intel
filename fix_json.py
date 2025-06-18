import json
import os

# Navnet på filen du vil fikse
input_filename = 'items_filtered.json'
# Navnet på den nye, korrigerte filen som blir laget
output_filename = 'items_filtered_REPARERT.json'

print(f"Prøver å reparere filen: {input_filename}")

# Sjekk om filen eksisterer
if not os.path.exists(input_filename):
    print(f"FEIL: Fant ikke filen '{input_filename}' i denne mappen.")
else:
    try:
        # Åpne den originale filen og prøv å laste innholdet
        with open(input_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Hvis lastingen var vellykket, lagre dataen til en ny fil
        with open(output_filename, 'w', encoding='utf-8') as f:
            # indent=4 gjør filen lesbar, ensure_ascii=False håndterer spesialtegn korrekt
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        print("-" * 50)
        print(f"SUCCESS: Filen ble lest og lagret på nytt uten feil.")
        print(f"En ny, garantert gyldig fil har blitt laget: '{output_filename}'")
        print("-" * 50)
        print("\nNeste steg:")
        print(f"1. Slett eller gi den gamle filen '{input_filename}' et nytt navn.")
        print(f"2. Gi den nye filen '{output_filename}' navnet '{input_filename}'.")
        print(f"3. Prøv å kjøre hovedprogrammet ditt på nytt.")

    except json.JSONDecodeError as e:
        # Hvis det er en feil, fortell nøyaktig hvor den er
        print("-" * 50)
        print(f"FEIL: Fant en formateringsfeil i '{input_filename}'.")
        print(f"Feilmelding: {e}")
        print(f"Feilen er på linje {e.lineno}, kolonne {e.colno}.")
        print("-" * 50)
    except Exception as e:
        print(f"En uventet feil oppstod: {e}")