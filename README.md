# BetonCheck Launcher

## Namestitev za razvoj

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

## Pred objavo

V `betoncheck_customer/settings.py` nastavi:

- `LICENSE_URL`
- `MODULES_URL`
- `UPDATES_URL`

V `config/` dodaj:

- `public_key.pem`
- `launcher_private_key.pem`

## Kako deluje

1. Uporabnik sprejme `LICENSE.txt`.
2. Vnese licencni kljuc.
3. Launcher prenese `licenses_signed.json`.
4. Preveri digitalni podpis z `public_key.pem`.
5. Preveri datum veljavnosti in dovoljene module.
6. Prenese potrebno `.bckx` datoteko.
7. Izbrani Excel se odpre.
