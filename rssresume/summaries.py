"""Génération des résumés textuels par catégorie."""

from __future__ import annotations

import json

from rssresume import console, cve
from rssresume.config import AppConfig
from rssresume import llm
from rssresume.models import Article, Note
from rssresume.profil import load_profil
from rssresume.text import no_article_message

FALLBACK_ARTICLES = 5
FALLBACK_EXCERPT_LENGTH = 180

#: Profondeur accordée à chaque article, par palier de volume : trois phrases
#: chacun sur vingt articles font un digest qu'on n'écoute pas jusqu'au bout.
DEPTH_TIERS = (
    (3, "Tu peux consacrer deux ou trois phrases à chaque sujet."),
    (8, "Une à deux phrases par sujet."),
)
DEPTH_DEFAULT = (
    "Une phrase par sujet, en fondant dans la même phrase ceux qui traitent de la même chose, "
    "et en gardant un peu plus de place pour les deux ou trois plus importants."
)

#: Le profil de pertinence est le même que celui du scoring : sans lui, le résumeur
#: hiérarchisait au hasard — il savait écrire pour l'oreille, pas pour QUI il écrivait.
SYSTEM_INTRO = (
    "Tu rédiges le résumé de veille quotidien de la personne dont voici le profil, et ce résumé "
    "est lu à voix haute. Ce profil est le SEUL critère de ce qui mérite d'être dit :\n\n"
)

SYSTEM_RULES = (
    "Privilégie ce qui a des conséquences concrètes pour ce profil : ce qui change, à quelle "
    "échéance, et ce que cela implique concrètement. Ce qui n'a aucune conséquence pour ce "
    "profil se dit en une incise, ou ne se dit pas. "
    "Tu parles comme quelqu'un qui raconte de vive voix ce qu'il a lu ce matin : des phrases "
    "enchaînées, un fil continu, une langue tenue pour l'oreille et non pour l'œil."
)


def system_prompt(profil: str | None = None) -> str:
    """Prompt système du digest audio, profil de pertinence inclus.

    Concaténation et non `format` : un profil venu de l'extérieur peut contenir des accolades.
    """
    return f"{SYSTEM_INTRO}{load_profil(profil)}\n\n{SYSTEM_RULES}"

STYLE_INSTRUCTION = (
    "Écris en prose continue, d'un sujet au suivant avec des transitions naturelles. "
    "Jamais de liste à puces, jamais de numérotation ni de « premièrement, deuxièmement », "
    "jamais de titre ni d'intertitre, aucun Markdown. "
    "Le texte est lu à voix haute : ne cite aucune URL, aucun nom de domaine, aucune adresse de "
    "site, et ne renvoie pas vers « le lien » ou « la source en description ». "
    "Tu t'adresses à une seule personne, celle du profil, qui écoute seule : dis « vous », "
    "jamais « bonjour à tous » ni « chers auditeurs », et jamais « nous »."
)

#: Le texte part tel quel en synthèse vocale : ce qui se lit bien à l'œil — incises,
#: parenthèses, longues chaînes de compléments — s'entend comme un débit plat. Le
#: rythme se joue ici, dans la phrase, pas dans les consignes de diction.
RHYTHM_INSTRUCTION = (
    "Écris pour l'oreille, en cherchant le rythme : alterne des phrases courtes et des phrases "
    "longues, et coupe toute phrase qui dépasse une trentaine de mots. Pas de parenthèses, pas "
    "d'incises entre tirets, pas de propositions relatives empilées, pas de longues chaînes de "
    "compléments de nom : une idée par phrase, le sujet et le verbe tôt, et l'information qui "
    "compte en fin de phrase, là où la voix appuie. Utilise les mots de liaison de l'oral — "
    "« du coup », « en clair », « à noter », « côté X » — plutôt que « par ailleurs » ou "
    "« en outre ». Varie les débuts de phrase : deux phrases de suite qui commencent pareil "
    "s'entendent immédiatement. Écris les nombres et les dates comme on les prononce — « quinze "
    "pour cent », « le 3 mars », pas « 15 % » ni « 03/03 ». Les identifiants de vulnérabilité et "
    "les numéros de version font exception : ils restent écrits tels quels, la diction s'en charge."
)

ANGLE_INSTRUCTION = (
    "Le champ « angle » dit en quoi l'article compte pour cet auditeur précis : c'est l'angle à "
    "prendre, la raison pour laquelle le sujet est dans le digest — à traduire dans tes phrases, "
    "jamais à recopier tel quel. Quand il manque, dégage l'angle du contenu."
)

ORDER_INSTRUCTION = (
    "Les articles arrivent regroupés par thématique (« thematique ») et dans l'ordre où ils "
    "doivent être racontés : garde cet ordre. Enchaîne les articles d'une même thématique sans "
    "les annoncer comme une rubrique, et marque le passage d'une thématique à la suivante par "
    "une transition d'une poignée de mots."
)

#: L'auditeur ne veut pas savoir qui a publié : le média n'est pas l'information, et
#: « … (CERT-FR, LeMagIT) » toutes les trois phrases hachait le texte à l'écoute. Les
#: sources restent dans l'email, sous le résumé, où elles se lisent au lieu de s'entendre.
NO_SOURCE_INSTRUCTION = (
    "Ne nomme jamais le média, le flux, le site ni le journaliste qui a publié l'information : "
    "ni entre parenthèses, ni en incise, ni sous la forme « selon X » ou « d'après X ». "
    "L'auditeur veut le fait, pas qui l'a rapporté. "
    "Une organisation nommée parce qu'elle EST l'acteur du fait — l'ANSSI qui publie un avis, "
    "la CNIL qui sanctionne, un éditeur qui corrige son produit — n'est pas une source : "
    "elle se dit normalement, c'est le sujet de la phrase."
)

MERGE_INSTRUCTION = (
    "Plusieurs articles peuvent couvrir le même événement depuis des sources différentes. "
    "Traite-les comme UN SEUL sujet : le fait dit une seule fois, et ce que chaque article apporte "
    "de plus gardé au même endroit. Ne produis jamais "
    "deux passages distincts pour le même fait, même quand les titres, les angles ou les "
    "formulations diffèrent. Les paliers de longueur ci-dessus se comptent en sujets après fusion, "
    "pas en articles reçus. "
    "Le même FAIT, pas le même thème : deux vulnérabilités différentes, deux décisions "
    "réglementaires différentes, deux incidents différents restent deux sujets distincts."
)

#: Les vulnérabilités sortent du régime commun : sur elles, la clarté factuelle passe avant
#: le style, et les règles de fusion comme les paliers de longueur les diluaient.
CVE_INSTRUCTION = (
    "Les vulnérabilités suivent une règle à part, où la précision prime sur le style. "
    "UNE vulnérabilité = UN sujet à elle seule : deux CVE différentes ne se fondent jamais dans la "
    "même phrase, même publiées le même jour, par la même source, sur le même produit. "
    "Pour chacune, dis simplement, dans cet ordre : l'identifiant, le produit et les versions "
    "touchés, ce que la faille permet, si elle est déjà exploitée, et ce qu'il y a à faire. "
    "Nomme toujours l'éditeur et le produit sous leur nom commercial exact, tel qu'il est écrit "
    "dans l'avis, et jamais sous une catégorie — « FortiOS », pas « le pare-feu » ; « VMware "
    "vCenter Server », pas « l'hyperviseur ». Donne les numéros de version en toutes lettres de "
    "l'avis : la plage touchée ET la version corrigée, « les versions 7.4.0 à 7.4.4, corrigé en "
    "7.4.5 ». C'est sur ces deux points — le nom exact et les versions — que l'auditeur décide "
    "s'il est concerné : ils passent avant tout le reste, et une CVE sans eux ne sert à rien. "
    "Quand l'avis nomme plusieurs produits ou plusieurs branches, cite-les tous. "
    "Une à deux phrases factuelles, sans mise en scène ni formule d'accroche, et ce quel que soit "
    "le nombre d'articles du jour — les paliers de longueur ci-dessus ne s'appliquent pas ici. "
    "Le champ « content » reprend le texte de la page de l'avis lorsqu'il a pu être lu : prends-y "
    "ces éléments plutôt que de paraphraser le titre. Ce qui n'y figure pas ne se dit pas : une "
    "version ou une date inventée sur un avis de sécurité est pire que l'absence d'information — "
    "quand l'avis ne donne pas les versions, dis-le en trois mots plutôt que de les deviner."
)

#: Une catégorie est un fichier audio à elle seule, écouté d'affilée : sans une phrase
#: qui l'ouvre et une qui la ferme, l'auditeur tombe au milieu d'un sujet et repart au
#: milieu d'un autre. Ces deux phrases sont jugées, pas récitées : elles disent ce que
#: vaut la journée dans cette catégorie, ce qu'aucun gabarit ne peut faire à l'avance.
OPENING_INSTRUCTION = (
    "Ouvre par UNE seule phrase courte, adressée à la personne qui écoute, qui situe la journée "
    "dans cette catégorie : combien il y a à dire, et ce qui en fait le poids — une urgence, une "
    "gravité, une surprise, ou au contraire une journée calme. Cette phrase se juge sur les "
    "articles que tu as sous les yeux, elle n'est jamais la même d'un jour à l'autre : "
    "« Trois avis ce matin, dont un qui vous concerne directement. », « Journée creuse, un seul "
    "sujet mais il compte. », « Beaucoup de bruit aujourd'hui, rien d'urgent. » "
    "Pas de salutation, pas de « voici le résumé du jour », pas de « dans cette catégorie », pas "
    "d'annonce du plan. Enchaîne ensuite directement sur le premier sujet."
)

CLOSING_INSTRUCTION = (
    "Termine par UNE seule phrase courte, adressée à la même personne, qui découle des sujets du "
    "jour et d'eux seuls : ce qu'il reste à faire, ce qui est à surveiller demain, ou le fait "
    "qu'il n'y a rien à faire — « Le correctif Fortinet, c'est la seule chose à faire "
    "aujourd'hui. », « Rien qui demande une action de votre part. », « À suivre demain, la "
    "décision de la CNIL. » "
    "Pas de conclusion passe-partout : ni rappel que la sécurité est un enjeu, ni appel à la "
    "vigilance, ni « restez attentif », ni résumé du résumé, ni « bonne journée » seul. "
    "Cette phrase et la phrase d'ouverture ne doivent pas dire la même chose."
)

class SummaryGenerator:
    def __init__(self, config: AppConfig):
        self._config = config

    def summarize(
        self, category: str, articles: list[Article], notes: dict[str, Note] | None = None
    ) -> str:
        """Résume la sélection ; `notes` porte la thématique et l'angle de chaque article."""
        if not articles:
            return self._summarize_fallback(category, articles)
        if self._config.uses_llm:
            return self._summarize_with_openai(category, articles, notes or {})
        return self._summarize_fallback(category, articles)

    def _summarize_with_openai(
        self, category: str, articles: list[Article], notes: dict[str, Note]
    ) -> str:
        # Les avis de vulnérabilité arrivent souvent réduits à leur titre : leur page
        # est lue avant le résumé, sans quoi la CVE ne serait que paraphrasée.
        articles = cve.enrich(articles)
        prompt_articles = [
            self._to_payload(article, notes.get(article.item_id)) for article in articles
        ]
        console.detail(f"résumé via l'API {self._config.summary_model} ({len(articles)} article(s))")
        return llm.chat(
            self._config.llm_base_url,
            self._config.llm_api_key,
            llm.DIGEST,
            system_prompt(self._config.profil),
            self._user_prompt(category, prompt_articles, len(articles)),
            model=self._config.summary_model,
        )

    @staticmethod
    def _to_payload(article: Article, note: Note | None) -> dict:
        """Article tel qu'il part au résumeur : son contenu, plus ce que le scoring en sait.

        L'angle et la thématique sont déjà payés par le scoring. Les jeter obligeait le
        résumeur à redécouvrir seul pourquoi chaque article était là.
        """
        payload = {
            "title": article.title,
            # Ni URL ni nom de flux : ce qui n'est pas dans le contexte ne peut pas être
            # prononcé. L'auditeur ne veut pas du média, et une URL vue dans le contexte
            # est une URL que le modèle peut recopier de travers. Les liens et les sources
            # de l'email viennent de `CategoryDigest.links`, pas du texte produit ici.
            "content": article.content_text,
        }
        if note:
            payload["thematique"] = note.thematique
            if note.angle:
                # Absent des articles dont le score vient du cache de tags.
                payload["angle"] = note.angle
        return payload

    def _user_prompt(self, category: str, prompt_articles: list[dict], article_count: int) -> str:
        return (
            f"Résume les articles du jour pour la catégorie '{category}' "
            f"en {self._config.summary_language}.\n\n"
            + STYLE_INSTRUCTION
            + "\n"
            + RHYTHM_INSTRUCTION
            + "\n"
            + self._depth_instruction(article_count)
            + "\n"
            + ANGLE_INSTRUCTION
            + "\n"
            + ORDER_INSTRUCTION
            + "\n"
            + MERGE_INSTRUCTION
            + "\n"
            + NO_SOURCE_INSTRUCTION
            + "\n"
            + CVE_INSTRUCTION
            + "\n"
            + OPENING_INSTRUCTION
            + "\n"
            + CLOSING_INSTRUCTION
            + "\n\nArticles:\n"
            + json.dumps(prompt_articles, ensure_ascii=False)
        )

    @staticmethod
    def _depth_instruction(article_count: int) -> str:
        """Longueur proportionnée au volume : le même texte pour 3 et pour 30 articles dilue tout."""
        for threshold, instruction in DEPTH_TIERS:
            if article_count <= threshold:
                return instruction
        return DEPTH_DEFAULT

    @staticmethod
    def _summarize_fallback(category: str, articles: list[Article]) -> str:
        if not articles:
            return no_article_message(category)

        console.detail(f"résumé local, sans IA ({len(articles)} article(s))")
        # Des phrases enchaînées, comme la version IA : ce texte part aussi en synthèse vocale.
        sentences = [
            f"Résumé du jour pour la catégorie {category}, {len(articles)} article(s) aujourd'hui."
        ]
        for article in articles[:FALLBACK_ARTICLES]:
            excerpt = article.content_text[:FALLBACK_EXCERPT_LENGTH].rstrip()
            # Pas plus de nom de flux ici que dans la version IA : la règle vient de
            # l'auditeur, pas du moteur, et les deux textes partent au même TTS.
            sentences.append(f"{article.title} : {excerpt}." if excerpt else f"{article.title}.")
        if len(articles) > FALLBACK_ARTICLES:
            sentences.append(
                f"{len(articles) - FALLBACK_ARTICLES} autre(s) article(s) complètent cette catégorie."
            )
        sentences.append("Bonne journée.")
        return " ".join(sentences)
