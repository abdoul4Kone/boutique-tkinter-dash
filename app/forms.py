"""Validation de saisie pour les formulaires ; les services restent l'autorité."""
import re
from datetime import date


def registration_errors(values):
    errors={}
    for key,caption in [('nom','nom'),('prenoms','prénoms')]:
        if not values[key].strip() or len(values[key].strip())>50:errors[key]=f'Renseignez vos {caption} (50 caractères maximum).'
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',values['email'].strip()) or len(values['email'].strip())>100:
        errors['email']='Saisissez une adresse électronique valide.'
    if not 12<=len(values['password'])<=256:errors['password']='Utilisez de 12 à 256 caractères.'
    if values['password']!=values['confirmation']:errors['confirmation']='Les deux mots de passe doivent correspondre.'
    try:
        birth=date.fromisoformat(values['birth'].strip())
        if not date(1900,1,1)<=birth<=date.today():raise ValueError
    except ValueError:errors['birth']='Date attendue : AAAA-MM-JJ, entre 1900 et aujourd’hui.'
    prefix=values['prefix'].strip().removeprefix('+');phone=values['phone'].strip()
    if not prefix.isascii() or not prefix.isdigit() or not 1<=len(prefix)<=3:errors['prefix']='Indicatif attendu, par exemple +225.'
    if not phone.isascii() or not phone.isdigit() or not 8<=len(phone)<=10:errors['phone']='Saisissez de 8 à 10 chiffres.'
    if len(values['prefix'].strip()+' '+phone)>15:errors['phone']='Le numéro avec indicatif ne doit pas dépasser 15 caractères.'
    return errors
