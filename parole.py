"""
parole.py — Versets bibliques liés aux statuts de prédiction
Auteur : Sossou Kouamé
L'administrateur peut ajouter librement des versets dans chaque catégorie.
"""

import random
import re

# ═══════════════════════════════════════════════════════════════════
#  SIGNATURE FINALE — ajoutée à la fin de chaque parole
# ═══════════════════════════════════════════════════════════════════
SIGNATURE = (
    "\n\n🙏 _Dieu est au contrôle_"
    "\n— **Sossou Kouamé** prediction 🔥"
)

# ═══════════════════════════════════════════════════════════════════
#  ✅0️⃣  GAGNÉ DIRECT — Grâce immédiate de Dieu
# ═══════════════════════════════════════════════════════════════════
PAROLES_GAGNE_R0 = [
    "🙌 « *Car c'est par grâce que vous êtes sauvés, par le moyen de la foi. Et cela ne vient pas de vous, c'est le don de Dieu.* » — Éph 2:8",
    "🌟 « *L'Éternel t'a accordé sa faveur avant même que tu demandes.* » — És 65:24",
    "🎯 « *Avant qu'ils appellent, Je répondrai ; ils parleront encore que J'aurai exaucé.* » — És 65:24",
    "⚡ « *Ce n'est pas à celui qui court, ni à celui qui fait des efforts, mais à Dieu qui fait grâce.* » — Rom 9:16",
    "🔥 « *Dieu a fait en sorte que tout concourt au bien de ceux qui l'aiment.* » — Rom 8:28",
    "🌈 « *Il a béni chacun de nous en Christ de toute bénédiction spirituelle.* » — Éph 1:3",
    "✨ « *La bonté et la grâce me suivront tous les jours de ma vie.* » — Ps 23:6",
    "🏆 « *Dieu a choisi les choses folles du monde pour confondre les sages.* » — 1 Cor 1:27",
    "💎 « *Car l'Éternel est un soleil et un bouclier ; il donne la grâce et la gloire.* » — Ps 84:12",
    "🎁 « *Toute bonne chose donnée, tout don parfait, descend d'en haut.* » — Jac 1:17",
    "🌅 « *Sa miséricorde se renouvelle chaque matin ; grande est ta fidélité !* » — Lam 3:23",
    "🦅 « *Ceux qui espèrent en l'Éternel renouvellent leur force. Ils montent avec des ailes comme des aigles.* » — És 40:31",
    "🙏 « *Je vous donnerai ce que votre cœur désire, si vous vous délectez en l'Éternel.* » — Ps 37:4",
    "💡 « *La lumière brille dans les ténèbres et les ténèbres ne l'ont pas reçue, mais toi tu l'as reçue !* » — Jn 1:5",
    "🎶 « *C'est l'Éternel qui agit : c'est admirable à nos yeux !* » — Ps 118:23",
    "🌺 « *Le Seigneur m'a répondu le jour où je l'ai appelé, Il a augmenté mes forces.* » — Ps 138:3",
    "⭐ « *Je t'ai choisi et je ne t'ai pas rejeté. Je suis avec toi.* » — És 41:9-10",
    "🏅 « *Dieu a renversé les puissants de leur trône et Il a élevé les humbles.* » — Luc 1:52",
    "🎊 « *L'Éternel est ma lumière et mon salut — de qui aurais-je peur ?* » — Ps 27:1",
    "🌻 « *Sa grâce m'a suffi car sa puissance s'accomplit dans la faiblesse.* » — 2 Cor 12:9",
    "🔑 « *Ce que l'Éternel ouvre, personne ne peut fermer. Sa faveur était sur toi.* » — Apo 3:7",
    "🌊 « *Il a commandé et la tempête s'est calmée. Ses vagues ont été apaisées.* » — Ps 107:29",
    "🌠 « *La victoire appartient à l'Éternel. Il te l'a accordée sans combat.* » — Prov 21:31",
    "🎯 « *Tout ce que je fais réussit car l'Éternel dirige mes pas.* » — Ps 1:3",
    "🔆 « *Je suis venu pour que vous ayez la vie, et que vous l'ayez en abondance.* » — Jn 10:10",
    "🌟 « *Dieu fait bien toutes choses. Il t'a accordé la victoire au premier instant.* » — Marc 7:37",
    "💫 « *Cherchez premièrement le royaume de Dieu, et tout le reste vous sera donné.* » — Matt 6:33",
    "🎉 « *Tu as transformé mon deuil en allégresse, tu as enlevé mon sac et tu m'as ceint de joie.* » — Ps 30:12",
    "🙌 « *L'Éternel combat pour toi ; toi, sois tranquille.* » — Ex 14:14",
    "🌈 « *Dieu t'a fait triompher sans que tu transpires. Sa grâce directe est ta portion.* » — 2 Cor 2:14",
    "⚡ « *Voici, je fais toutes choses nouvelles. Ce que J'ai promis, Je l'accomplis sur-le-champ.* » — Apo 21:5",
    "💪 « *Ne t'effraye pas car Je suis ton Dieu ; Je t'ai affermi, Je t'ai aidé.* » — És 41:10",
    "🏆 « *Dieu nous donne la victoire par notre Seigneur Jésus-Christ.* » — 1 Cor 15:57",
    "🌺 « *Tu as été fidèle, entre dans la joie de ton Seigneur.* » — Matt 25:21",
    "🎁 « *Toute grâce est l'œuvre de Dieu seul. Il t'a couronné ce soir.* » — Ps 103:4",
    "🔥 « *Je me rappellerai les hauts faits de l'Éternel ; oui, je me souviendrai de tes miracles d'autrefois.* » — Ps 77:12",
    "🌅 « *C'est lui qui donne la force d'acquérir des richesses, pour confirmer son alliance.* » — Deut 8:18",
    "✨ « *Pour toi qui crains mon nom, se lèvera le soleil de la justice avec la guérison dans ses rayons.* » — Mal 4:2",
    "🦅 « *Je suis avec toi pour te délivrer, dit l'Éternel.* » — Jér 1:19",
    "🎶 « *Béni soit l'Éternel qui ne nous a pas livrés en proie à leurs dents !* » — Ps 124:6",
    "💎 « *Tu ouvres ta main, et tu rassasies à souhait tout ce qui a vie.* » — Ps 145:16",
    "🌻 « *Car c'est moi qui connais les projets que j'ai formés sur vous, projets de paix et non de malheur.* » — Jér 29:11",
    "🌠 « *L'Éternel accomplit son œuvre — admire ce qu'Il a fait pour toi directement.* » — Ps 111:2",
    "🎊 « *Dieu t'a exaucé avant la fin de ta prière. C'est sa manière d'agir.* » — Dan 9:23",
    "🌊 « *Il a répondu à ma prière et m'a accordé ma demande.* » — Ps 20:5",
    "🔑 « *Heureux l'homme qui met sa confiance en l'Éternel.* » — Ps 34:9",
    "🎯 « *Tout ce que vous demanderez en mon nom, je le ferai.* » — Jn 14:13",
    "💡 « *Dieu a dit oui, et sur-le-champ sa parole s'est accomplie.* » — 2 Cor 1:20",
    "⭐ « *L'Éternel est bon pour ceux qui espèrent en lui. Sa grâce est venue ce soir.* » — Lam 3:25",
    "🏅 « *La bénédiction de l'Éternel enrichit, et il n'y joint aucune peine.* » — Prov 10:22",
    "🙌 « *Je ne te laisserai point et je ne t'abandonnerai point.* » — Jos 1:5",
    "🎵 « *Dieu a mis dans ma bouche un chant nouveau. Sa grâce directe est mon cantique !* » — Ps 40:4",
    "🌟 « *Sa droite et son bras saint lui ont donné la victoire.* » — Ps 98:1",
    "🏆 « *Il n'y a pas eu de peine, il n'y a eu que la grâce — et c'est Dieu.* » — Ps 118:16",
    "🌺 « *Je savais que tu m'exauces toujours.* » — Jn 11:42",
    "💫 « *Par la foi tu as vu la victoire. Dieu honore la foi immédiate.* » — Héb 11:1",
    "🔆 « *Tu as frappé à la porte et immédiatement elle s'est ouverte.* » — Matt 7:8",
    "🎉 « *Le Seigneur a accompli pour toi de grandes choses.* » — Ps 126:3",
    "🌈 « *J'ai demandé, j'ai cherché, j'ai frappé — et la réponse fut immédiate.* » — Matt 7:7",
    "⚡ « *Il n'est pas lent à accomplir ses promesses. Il était déjà prêt.* » — 2 Pi 3:9",
    "💪 « *Le Seigneur est proche de tous ceux qui l'invoquent avec sincérité.* » — Ps 145:18",
    "🌻 « *C'est l'Éternel qui a fait cela — et c'est admirable à nos yeux.* » — Ps 118:23",
    "🎵 « *Il a mis un chant nouveau dans ma bouche — un chant de louange à notre Dieu.* » — Ps 40:3",
    "🌿 « *Goûtez et voyez combien l'Éternel est bon. Heureux l'homme qui se confie en lui !* » — Ps 34:9",
    "🏅 « *Je t'aime, Éternel, ma force ! L'Éternel est mon rocher, ma forteresse.* » — Ps 18:2",
]

# ═══════════════════════════════════════════════════════════════════
#  ✅1️⃣  GAGNÉ R1 — Victoire après une première persévérance
# ═══════════════════════════════════════════════════════════════════
PAROLES_GAGNE_R1 = [
    "💪 « *Sois fort et courageux ! N'aie pas peur car l'Éternel ton Dieu est avec toi.* » — Jos 1:9",
    "🔥 « *Nous savons que la tribulation produit la persévérance.* » — Rom 5:3",
    "🌟 « *Heureux l'homme qui supporte patiemment la tentation car il recevra la couronne de vie.* » — Jac 1:12",
    "🏆 « *Celui qui persévère jusqu'à la fin sera sauvé.* » — Matt 24:13",
    "⭐ « *Continuez, ne vous relâchez pas, car votre travail aura sa récompense.* » — 2 Chr 15:7",
    "🌈 « *Ne te laisse pas vaincre par le mal, mais surmonte le mal par le bien.* » — Rom 12:21",
    "🎯 « *Tu es tombé une fois, mais tu t'es relevé — et c'est là que Dieu t'a récompensé !* » — Prov 24:16",
    "💡 « *La persévérance forme le caractère, et le caractère l'espérance.* » — Rom 5:4",
    "🌺 « *À celui qui vaincra, je donnerai à manger de l'arbre de vie.* » — Apo 2:7",
    "🦅 « *Il bande mes pieds comme ceux des biches et me fait marcher sur mes lieux élevés.* » — Ps 18:34",
    "🌅 « *L'affliction du juste est grande, mais l'Éternel le délivre de toutes.* » — Ps 34:20",
    "💎 « *Ce qui est né de Dieu vainc le monde ; et la victoire qui a vaincu le monde, c'est notre foi.* » — 1 Jn 5:4",
    "🎁 « *Je suis persuadé que celui qui a commencé en toi cette bonne œuvre la rendra parfaite.* » — Phil 1:6",
    "🌊 « *Il a dit non en première instance, mais la foi a insisté et Dieu a cédé à ta confiance.* » — Luc 18:7",
    "🔑 « *Frappez et l'on vous ouvrira. La deuxième frappe a tout changé !* » — Matt 7:7",
    "✨ « *L'Éternel ton Dieu est au milieu de toi, un héros qui sauve. Il s'est réjoui de toi.* » — Soph 3:17",
    "🎶 « *Je te bénirai et tu seras une bénédiction. Tiens bon.* » — Gen 12:2",
    "🌻 « *La joie de l'Éternel est votre force — même après un premier refus.* » — Néh 8:10",
    "🏅 « *L'Éternel est fidèle ; il vous affermira et vous gardera du mal.* » — 2 Thes 3:3",
    "🙌 « *Revêtez-vous de toutes les armes de Dieu. Tenez ferme — la victoire arrive !* » — Éph 6:13",
    "🔆 « *Dieu ne tarde pas à accomplir ce qu'il a promis. Il t'a rendu justice.* » — Luc 18:8",
    "🌠 « *Je sais que l'Éternel m'accordera la victoire. Sa parole ne peut manquer.* » — Ps 20:7",
    "⚡ « *Ne vous découragez pas : au moment fixé, la moisson viendra — et elle est venue !* » — Gal 6:9",
    "💪 « *Tu as lutté avec Dieu et avec les hommes, et tu as été vainqueur.* » — Gen 32:28",
    "🎉 « *Il n'a pas méprisé ni rejeté la souffrance du malheureux ; Il a entendu.* » — Ps 22:25",
    "🌟 « *L'espérance ne confond point, car l'amour de Dieu est répandu dans nos cœurs.* » — Rom 5:5",
    "🎊 « *Ne crains pas, car je t'ai racheté, je t'ai appelé par ton nom : tu es à moi.* » — És 43:1",
    "🔥 « *Ta foi t'a sauvé. Va en paix. Le premier pas de persévérance t'a tout apporté.* » — Luc 7:50",
    "🌺 « *À celui qui vaincra je donnerai de la manne cachée.* » — Apo 2:17",
    "💡 « *Ne pleure pas, car le lion de la tribu de Juda a vaincu — et tu es avec lui.* » — Apo 5:5",
    "🎯 « *Soyez fermes, inébranlables, toujours abondants dans l'œuvre du Seigneur.* » — 1 Cor 15:58",
    "🌈 « *Tu as passé par le premier test. Dieu t'a vu tenir — et Il t'a accordé la récompense.* » — Ps 11:5",
    "🦅 « *Après la première attente, la délivrance est venue. Loue l'Éternel !* » — Ps 31:8",
    "🌅 « *Ta lumière se lèvera dans les ténèbres et l'obscurité sera comme le midi.* » — És 58:10",
    "⭐ « *Le Seigneur ramènera les captifs de son peuple. Jacob se réjouira, Israël sera dans l'allégresse.* » — Ps 53:7",
    "💎 « *Dieu a tenu sa promesse après la première épreuve. Sa fidélité est grande.* » — Lam 3:23",
    "🏆 « *Voici, j'ai mis devant toi une porte ouverte que personne ne peut fermer.* » — Apo 3:8",
    "🎁 « *Reviens à moi et je reviendrai à toi, dit l'Éternel des armées.* » — Mal 3:7",
    "🌊 « *Tu as cherché et tu as trouvé. Le premier rattrapage t'a ouvert la porte.* » — Matt 7:8",
    "🔑 « *L'Éternel affermit les pas de l'homme dont Il prend plaisir à la voie.* » — Ps 37:23",
    "✨ « *Dieu n'abandonne pas ceux qui le cherchent. Ta persévérance a payé.* » — Ps 9:11",
    "🎶 « *Chantez à l'Éternel un chant nouveau car Il a fait des merveilles.* » — Ps 98:1",
    "🌻 « *Je t'ai fortifié bien que tu ne me connaisses pas. Je veille sur toi.* » — És 45:5",
    "🏅 « *Ce sont les épreuves qui produisent la persévérance, la persévérance la vertu éprouvée.* » — Rom 5:3-4",
    "🙌 « *Au premier combat, tu n'as pas abandonné. C'est pourquoi Dieu t'a récompensé.* » — 2 Tim 4:7",
    "🔆 « *Ne perds pas ta confiance car elle a une grande récompense.* » — Héb 10:35",
    "🌠 « *L'Éternel t'a fait triompher sur tes ennemis.* » — Deut 28:7",
    "⚡ « *La patience accomplit une œuvre parfaite. Tu l'as vue en R1 ce soir.* » — Jac 1:4",
    "💪 « *Je peux tout par celui qui me fortifie. Le R1 en est la preuve.* » — Phil 4:13",
    "🎉 « *Loué soit Dieu qui ne nous a pas laissé pour proie à leurs dents.* » — Ps 124:6",
    "🌟 « *Dieu t'a couronné de bonté et de miséricorde après le premier rattrapage.* » — Ps 103:4",
    "🎊 « *Sa miséricorde est grande envers nous. Loue l'Éternel !* » — Ps 117:2",
    "🔥 « *Le Seigneur est avec les brisés de cœur. Il n'a pas abandonné ta demande.* » — Ps 34:19",
    "🌺 « *La foi déplace les montagnes. Au R1, ta foi a parlé.* » — Matt 17:20",
    "💡 « *Demandez et vous recevrez. Le R1 prouve que Dieu t'a finalement accordé la grâce.* » — Jn 16:24",
    "🎯 « *Persévère dans tes prières — le R1 est ton témoignage ce soir.* » — Col 4:2",
    "🌈 « *Celui qui croit ne sera point confus — tu l'as vu après le premier essai.* » — Rom 10:11",
    "🦅 « *Tiens ferme, ne te relâche pas ! Car ton œuvre sera récompensée.* » — 2 Chr 15:7",
    "🌅 « *Après la pluie, le beau temps. Après le premier refus, la victoire !* » — Job 8:21",
    "⭐ « *Tu te souviens que tu as failli perdre courage, mais tu as tenu — et voilà la victoire !* » — Héb 12:1",
    "💎 « *La couronne de vie est pour ceux qui ont supporté l'épreuve.* » — Jac 1:12",
    "🌊 « *Voici, l'Éternel a prononcé, et il accomplira sa parole. Il tient ce qu'il promet.* » — Nomb 23:19",
    "🎊 « *Celui qui commence une bonne œuvre en toi la rendra parfaite. Ne lâche pas.* » — Phil 1:6",
    "🌼 « *Ta foi t'a sauvé. Va en paix et sois guéri de ta maladie.* » — Marc 5:34",
]

# ═══════════════════════════════════════════════════════════════════
#  ✅2️⃣  GAGNÉ R2 — Victoire après deux épreuves
# ═══════════════════════════════════════════════════════════════════
PAROLES_GAGNE_R2 = [
    "💪 « *Combats le bon combat de la foi. Deux fois tu as tenu — et tu as gagné !* » — 1 Tim 6:12",
    "🔥 « *Voici, je t'ai éprouvé dans la fournaise de l'affliction. Et tu es sorti pur !* » — És 48:10",
    "🌟 « *L'Éternel fait grâce à celui qui patiente jusqu'à la troisième occasion.* » — Lam 3:26",
    "🏆 « *Soyez patients, affermissez vos cœurs, car l'avènement du Seigneur est proche.* » — Jac 5:8",
    "⭐ « *Après deux épreuves, Dieu t'a ouvert la porte. C'est Sa signature.* » — Ps 107:13",
    "🌈 « *Si tu passes par les eaux, je serai avec toi. Si tu passes par les rivières, elles ne te submergeront pas.* » — És 43:2",
    "🎯 « *Dieu t'a mis dans la fournaise deux fois, mais tu en es sorti sans odeur de feu !* » — Dan 3:27",
    "💡 « *La patience produit une œuvre parfaite. Deux fois tu as persisté.* » — Jac 1:4",
    "🌺 « *Ne sois pas vaincu par le mal. Deux fois le mal t'a frappé, mais tu l'as surmonté.* » — Rom 12:21",
    "🦅 « *Deux fois la tempête, mais Dieu était dans la barque. La paix est venue.* » — Marc 4:39",
    "🌅 « *Deux fois le refus, mais la troisième fois l'Éternel t'a parlé.* » — 1 Sam 3:8",
    "💎 « *Ta foi a été éprouvée deux fois et elle a tenu. Elle vaut plus que l'or.* » — 1 Pi 1:7",
    "🎁 « *L'argent éprouvé au creuset — ta foi a passé deux fois l'épreuve.* » — Ps 12:7",
    "🌊 « *La vague a frappé deux fois, mais le rocher a tenu. Tu es ce rocher.* » — Matt 7:25",
    "🔑 « *Deux fois l'obscurité, mais la lumière est venue. Gloire à Dieu !* » — Jn 1:5",
    "✨ « *Ne te décourage pas. L'Éternel ta fortifié deux fois pour te conduire à la victoire.* » — És 41:10",
    "🎶 « *Je t'ai éprouvé comme on éprouve l'argent. Deux fois au feu — tu es pur !* » — Zach 13:9",
    "🌻 « *Il a dit : cherche ma face. J'ai cherché deux fois et Il m'a répondu.* » — Ps 27:8",
    "🏅 « *Après deux longues nuits, le matin de la joie est venu.* » — Ps 30:6",
    "🙌 « *Deux fois Pierre a nié, mais Jésus ne l'a pas abandonné. Dieu ne t'abandonne pas non plus.* » — Luc 22:61-62",
    "🔆 « *Béni soit l'Éternel qui renouvelle ta force après chaque épreuve.* » — És 40:29",
    "🌠 « *Après deux combats, la victoire est d'autant plus douce. Goûte-la !* » — Ps 34:9",
    "⚡ « *Deux fois l'obscurité, mais Dieu avait tout calculé pour ta gloire.* » — Rom 8:28",
    "💪 « *Job a perdu deux fois, mais Dieu lui a tout rendu au double. Ta victoire vaut double !* » — Job 42:10",
    "🎉 « *L'Éternel m'a répondu après la deuxième prière. Sa grâce ne faillit jamais.* » — Ps 118:5",
    "🌟 « *Deux fois le chemin fut barré, mais Dieu a ouvert un autre passage.* » — És 43:19",
    "🎊 « *Deux fois dans la tempête avec Paul, mais Dieu avait dit : aucun ne périra.* » — Ac 27:24",
    "🔥 « *Tu as traversé deux rivières. L'Éternel était avec toi à chaque pas.* » — Jos 3:17",
    "🌺 « *Même quand la vigne ne fleurit pas deux fois, je me réjouirai en l'Éternel.* » — Hab 3:17-18",
    "💡 « *Deux fois dans l'obscurité mais tu n'as pas lâché ta foi — et Dieu t'a honoré.* » — Héb 11:6",
    "🎯 « *Dieu a permis deux épreuves pour montrer Sa gloire dans ta victoire finale.* » — Jn 11:4",
    "🌈 « *Deux fois l'enfant de Sunam mourut, mais Élisée pria deux fois et il ressuscita.* » — 2 Rois 4:35",
    "🦅 « *Deux fois dans l'arène, mais le lion a été fermé. Tu sors vivant !* » — Dan 6:23",
    "🌅 « *Après la deuxième nuit, l'ange t'a touché et t'a dit : lève-toi et mange.* » — 1 Rois 19:7",
    "⭐ « *Deux fois Gédéon a demandé un signe, et deux fois Dieu a répondu. Ta foi est confirmée.* » — Jug 6:39",
    "💎 « *Éprouvé deux fois au feu, tu en es sorti victorieux. Tu es de l'or pur !* » — Job 23:10",
    "🏆 « *Deux fois dans la vallée de l'ombre, mais l'Éternel était là.* » — Ps 23:4",
    "🎁 « *Après deux tentatives, David a frappé Goliath. Ta confiance a vaincu.* » — 1 Sam 17:49",
    "🌊 « *Deux fois les mers se sont levées, mais Dieu t'a conduit sain et sauf.* » — Ex 14:22",
    "🔑 « *Deux fois dans le puits comme Joseph, mais la délivrance est venue.* » — Gen 37:24",
    "✨ « *Ta patience de deux cycles t'a valu la couronne. Bénis l'Éternel !* » — Jac 1:12",
    "🎶 « *Deux fois au bord du gouffre, mais l'Éternel a tenu ta main.* » — Ps 73:23",
    "🌻 « *Deux épreuves pour une seule victoire — le plan de Dieu est parfait.* » — Jér 29:11",
    "🏅 « *Ne perds pas courage car tu as tenu deux fois. Quelle foi !* » — Héb 10:36",
    "🙌 « *Deux fois la croix s'est alourdie, mais tu n'as pas abandonné. Tu mérites la victoire.* » — Luc 9:23",
    "🔆 « *Deux fois Pierre a marché sur l'eau, une fois il a coulé — mais Jésus l'a saisi. Il t'a saisi aussi.* » — Matt 14:31",
    "🌠 « *Dieu a dit deux fois à Élie : lève-toi. Et toi aussi, tu t'es levé.* » — 1 Rois 19:7",
    "⚡ « *Deux fois dans la fournaise, mais le quatrième homme était là. Dieu était avec toi.* » — Dan 3:25",
    "💪 « *Deux fois tombé, deux fois relevé. C'est cela la foi victorieuse.* » — Prov 24:16",
    "🎉 « *Après deux épreuves, la joie est encore plus grande. Savoure ta victoire.* » — Ps 126:5",
    "🌟 « *Deux fois dans l'obscurité mais tu as toujours vu la lumière au bout.* » — Jn 8:12",
    "🎊 « *Ta patience de deux rondes est un témoignage pour tous ceux qui t'entourent.* » — Héb 12:1",
    "🔥 « *Deux fois l'ennemi t'a attaqué, deux fois Dieu t'a défendu.* » — Ps 34:8",
    "🌺 « *Deux fois le doute a frappé, mais ta foi a résisté. Dieu t'honore.* » — Matt 21:22",
    "💡 « *Deux fois dans la nuit de Gethsémani, mais la résurrection vient toujours le matin.* » — Ps 30:6",
    "🎯 « *La persévérance de deux rondes te vaut aujourd'hui une récompense double.* » — Job 42:10",
    "🌈 « *Dieu a attendu ta deuxième tentative pour intervenir et montrer sa gloire.* » — Jn 11:6",
    "🦅 « *Deux fois dans la vallée, mais tu n'as pas abandonné. Dieu t'a vu.* » — Ps 18:3",
    "🌅 « *Après le deuxième refus de Pharaon, la délivrance d'Israël était imminente.* » — Ex 8:1",
    "⭐ « *Deux fois tu as frappé à la porte, et au deuxième coup Dieu a dit : entre !* » — Matt 7:8",
    "💎 « *Deux épreuves, une victoire. C'est la méthode de Dieu.* » — 1 Cor 10:13",
    "🌸 « *Après deux essais, Dieu a ouvert une porte qu'aucun homme ne peut fermer.* » — Apo 3:7",
    "🎯 « *Deux fois tu as tendu la main vers Lui, et deux fois Il t'a tendu la sienne.* » — Ps 138:7",
    "🕊️ « *La double épreuve produit une double gloire. C'est le calcul du ciel.* » — 2 Cor 4:17",
]

# ═══════════════════════════════════════════════════════════════════
#  ✅3️⃣  GAGNÉ R3 — Victoire ultime après trois épreuves
# ═══════════════════════════════════════════════════════════════════
PAROLES_GAGNE_R3 = [
    "🔥 « *Shadrach, Meshach et Abed-Nego sont entrés dans la fournaise ardente — et en sont sortis victorieux ! Toi aussi !* » — Dan 3:25",
    "🏆 « *Trois fois Paul a demandé la délivrance — et Dieu a dit : ma grâce te suffit. Et tu as gagné quand même !* » — 2 Cor 12:8-9",
    "⭐ « *Trois fois Pierre a nié, mais Jésus l'a restauré trois fois aussi. Ta triple épreuve est vaincue.* » — Jn 21:17",
    "💪 « *Trois fois Samson fut tenté par Dalila, mais sa force ultime vint de Dieu. Tu es comme lui.* » — Jug 16:28",
    "🌟 « *Jonas a passé trois jours dans le ventre du poisson — et en est sorti victorieux. Tu en es sorti aussi !* » — Jon 1:17",
    "🌈 « *Trois jours dans le tombeau, mais la résurrection est venue ! Ta victoire en R3 est une résurrection !* » — Matt 28:6",
    "🎯 « *Trois fois Gédéon a tenu bon, et Dieu a dispersé l'armée ennemie. Loue l'Éternel !* » — Jug 7:21",
    "💡 « *Après trois rondes, Dieu t'a accordé la victoire. C'est le signe de la Trinité — Père, Fils, Esprit !* » — Matt 28:19",
    "🌺 « *Élie a versé de l'eau sur l'autel trois fois, et le feu est quand même tombé. Ta victoire est celle du feu divin !* » — 1 Rois 18:34-38",
    "🦅 « *Trois fois dans l'adversité, mais trois fois Dieu t'a défendu. Tu es son champion !* » — Ps 91:14",
    "🌅 « *Trois fois dans la nuit, mais l'aurore est venue. Tu as vu l'aurore de Dieu !* » — Ps 30:6",
    "💎 « *L'or est éprouvé trois fois au creuset — et tu es resssorti victorieux. Tu es de l'or pur !* » — 1 Pi 1:7",
    "🎁 « *Trois fois la porte semblait fermée, mais au troisième coup elle s'est ouverte. C'est le timing de Dieu.* » — Luc 18:5",
    "🌊 « *Les trois amis de Job ont dit que Dieu l'avait abandonné — mais Dieu a restauré Job. Gloire !* » — Job 42:10",
    "🔑 « *Après trois demandes, le Père a dit oui — parce que ta foi a traversé toutes les tempêtes.* » — Matt 7:8",
    "✨ « *Trois fois tu as lutté, trois fois tu as persisté — et Dieu t'a couronné.* » — Jac 1:12",
    "🎶 « *C'est en passant par le feu et par l'eau que tu es entré dans une large aisance.* » — Ps 66:12",
    "🌻 « *Job a tout perdu trois fois mais Dieu l'a béni au double. Ta victoire vaut triple !* » — Job 42:10",
    "🏅 « *Trois jours de marche dans le désert avant de trouver de l'eau. Tu as trouvé ton eau !* » — Ex 15:22-25",
    "🙌 « *Trois fois nu dans la tempête avec Paul, et trois fois Dieu a dit : il n'y aura pas de perte.* » — Ac 27:24",
    "🔆 « *Après la triple épreuve, la triple bénédiction t'appartient.* » — Deut 28:2",
    "🌠 « *Trois fois dans la détresse, trois fois l'Éternel m'a délivré. Loue son nom !* » — Ps 107:6",
    "⚡ « *Tu as passé par le feu et par l'eau, mais l'Éternel t'a fait sortir au large.* » — Ps 66:12",
    "💪 « *Après trois jours de jeûne, Esther est allée devant le roi et a obtenu la victoire.* » — Est 5:2",
    "🎉 « *Trois fois Dieu a éprouvé ta foi, et trois fois tu n'as pas lâché. Tu mérites la couronne !* » — 2 Tim 4:8",
    "🌟 « *Trois fois dans la fournaise — et le quatrième était là avec toi. Dieu ne t'a jamais quitté.* » — Dan 3:25",
    "🎊 « *Après trois rondes, la victoire a la saveur de l'éternité. Goûte-la !* » — Ps 34:9",
    "🔥 « *Trois fois l'ennemi a dit : tu ne gagneras pas. Et trois fois Dieu a dit : si, Il gagnera !* » — Rom 8:37",
    "🌺 « *Trois rondes, trois tentatives — et Dieu t'a honoré. C'est un témoignage !* » — 1 Sam 17:45",
    "💡 « *Le troisième jour, les noces de Cana ont eu lieu — et l'eau est devenue vin. Ta victoire est un miracle !* » — Jn 2:1",
    "🎯 « *Trois fois tombé, trois fois relevé — et la quatrième fois, tu as gagné debout !* » — Prov 24:16",
    "🌈 « *Trois fois la pluie n'est pas venue, mais la septième fois le nuage est apparu. En R3, ton nuage est venu.* » — 1 Rois 18:44",
    "🦅 « *Trois fois dans le ventre de la baleine — mais la prière d'au fond a été entendue.* » — Jon 2:2",
    "🌅 « *Après trois rondes de persévérance, ta foi a vaincu le monde.* » — 1 Jn 5:4",
    "⭐ « *Dieu a attendu le troisième round pour révéler toute sa gloire dans ta victoire.* » — Jn 11:4",
    "💎 « *Trois fois dans le creuset — tu en es sorti comme de l'argent affiné.* » — Zach 13:9",
    "🏆 « *Après trois épreuves consécutives, ta victoire vaut dix fois plus. Savoure !* » — Dan 1:20",
    "🎁 « *Trois fois dans l'obscurité, mais la lumière de l'Éternel ne s'est jamais éteinte.* » — Ps 119:105",
    "🌊 « *Trois fois submergé par les vagues, mais l'Éternel t'a tendu la main à chaque fois.* » — Matt 14:31",
    "🔑 « *Trois demandes pressantes — et Dieu a finalement dit : Oui, mon enfant, entre !* » — Luc 11:8",
    "✨ « *Trois fois dans la vallée de la mort, mais tu n'as craint aucun mal car Il était avec toi.* » — Ps 23:4",
    "🎶 « *Triple épreuve, triple victoire. Car l'Éternel est Dieu des armées.* » — 1 Sam 17:45",
    "🌻 « *Après le troisième essai, Dieu a ouvert les cieux sur toi.* » — Mal 3:10",
    "🏅 « *Tu as combattu le bon combat trois fois — maintenant la couronne de justice t'est réservée.* » — 2 Tim 4:7-8",
    "🙌 « *Trois rondes de foi et Jéricho est tombée. Ta victoire est la chute de Jéricho !* » — Jos 6:20",
    "🔆 « *Trois fois dans le désert avec Moïse — mais la Terre Promise est toujours là.* » — Ex 3:17",
    "🌠 « *Triple persévérance, triple récompense. C'est le calcul de Dieu.* » — Jac 1:12",
    "⚡ « *Trois fois dans la nuit sans étoiles, mais l'aurore a toujours le dernier mot.* » — Ps 30:6",
    "💪 « *Tu as marché trois fois autour du problème comme Israël a marché autour de Jéricho — et les murs sont tombés !* » — Jos 6:15",
    "🎉 « *Trois épreuves pour un seul trophée — mais quel trophée ! La victoire de Dieu !* » — 2 Cor 2:14",
    "🌟 « *Trois fois Dieu a dit : c'est assez. Mais Il t'a quand même conduit à la victoire.* » — 2 Cor 12:8-9",
    "🎊 « *La triple épreuve révèle la triple grâce de Dieu. Père — Force. Fils — Victoire. Esprit — Joie.* » — Matt 28:19",
    "🔥 « *Tu as supporté le triple feu de la tribulation. Tu es maintenant de l'or pur.* » — Mal 3:3",
    "🌺 « *Trois fois dans les flammes et le quatrième homme était là. Il était là pour toi aussi.* » — Dan 3:25",
    "💡 « *Après le troisième essai, Dieu a montré que rien n'est impossible à celui qui croit.* » — Luc 1:37",
    "🎯 « *Ta persévérance de trois rondes a édifié ta foi comme une montagne.* » — Matt 17:20",
    "🌈 « *Trois fois dans l'abîme — et trois fois Dieu a ouvert le chemin du retour.* » — Jon 2:7",
    "🦅 « *La foi qui traverse trois épreuves est la foi qui déplace les montagnes.* » — Marc 11:23",
    "🌅 « *Après le troisième rattrapage, l'Éternel t'a accordé le repos de la victoire.* » — Ex 33:14",
    "⭐ « *Trois fois dans la fournaise — tu en es sorti sans odeur de feu. Gloire à Dieu !* » — Dan 3:27",
    "💎 « *Ta foi triomphante en R3 est un témoignage qui durera éternellement.* » — Héb 11:6",
    "🌻 « *Trois fois dans le désert et trois fois l'eau est sortie du rocher. Dieu ne manque jamais.* » — Ex 17:6",
    "🎶 « *Après la triple nuit, le matin de Pâques est venu. Ta victoire est une résurrection.* » — Matt 28:1",
    "🔆 « *Trois cycles de foi — trois preuves que Dieu est fidèle à sa parole.* » — 2 Tim 2:13",
]

# ═══════════════════════════════════════════════════════════════════
#  ❌  PERDU — Confort, compassion, encouragement
# ═══════════════════════════════════════════════════════════════════
PAROLES_PERDU = [
    "🤍 « *L'Éternel est proche de ceux qui ont le cœur brisé, et il sauve ceux qui ont l'esprit dans l'abattement.* » — Ps 34:19",
    "🌿 « *Il guérit ceux qui ont le cœur brisé, et il bande leurs blessures.* » — Ps 147:3",
    "☁️ « *Les pleurs durent une nuit, mais la joie vient le matin.* » — Ps 30:6",
    "🕊️ « *Venez à moi, vous qui êtes fatigués et chargés, et je vous donnerai du repos.* » — Matt 11:28",
    "🌱 « *Ce que tu vis maintenant n'est pas la fin. C'est un nouveau commencement.* » — Apo 21:5",
    "💙 « *Je sais que les pensées que j'ai à votre égard sont des pensées de paix.* » — Jér 29:11",
    "🌤️ « *Il ne cassera pas le roseau froissé, il n'éteindra pas le lumignon qui faiblit.* » — És 42:3",
    "🙏 « *Confie-toi en l'Éternel de tout ton cœur, et ne t'appuie pas sur ta sagesse.* » — Prov 3:5",
    "🌿 « *L'Éternel est bon, il est un refuge au jour de la détresse.* » — Nah 1:7",
    "💜 « *Je t'ai aimé d'un amour éternel; c'est pourquoi je te conserve ma bienveillance.* » — Jér 31:3",
    "🌦️ « *Ne te réjouis pas à mon sujet, mon ennemie ! Car si je suis tombée, je me relèverai.* » — Mic 7:8",
    "🕊️ « *L'Éternel est mon berger: je ne manquerai de rien.* » — Ps 23:1",
    "🌻 « *Tu ne seras jamais éprouvé au-delà de tes forces. Il y a toujours une issue.* » — 1 Cor 10:13",
    "🌱 « *Dieu fait concourir toutes choses au bien de ceux qui l'aiment.* » — Rom 8:28",
    "💚 « *Cette légère et momentanée tribulation nous prépare un poids éternel de gloire.* » — 2 Cor 4:17",
    "🌊 « *Quand tu traverses les eaux, je suis avec toi. Ne crains pas.* » — És 43:2",
    "🕊️ « *Dieu essuiera toute larme de leurs yeux. La douleur aura une fin.* » — Apo 21:4",
    "🌿 « *Il donne de la force à celui qui est fatigué, et il augmente la vigueur de celui qui est à bout de forces.* » — És 40:29",
    "☁️ « *Tu n'es pas abandonné. Dieu connaît le chemin que tu fais.* » — Job 23:10",
    "💙 « *Je marcherai au milieu de la détresse, tu me feras revivre.* » — Ps 138:7",
    "🌤️ « *L'Éternel est proche de tous ceux qui l'invoquent, de tous ceux qui l'invoquent avec sincérité.* » — Ps 145:18",
    "🙏 « *Portez les fardeaux les uns des autres, et accomplissez ainsi la loi de Christ.* » — Gal 6:2",
    "💜 « *Car l'Éternel ne rejette pas pour toujours. S'il afflige, il fait aussi miséricorde.* » — Lam 3:31-32",
    "🌱 « *Il n'a point de pouvoir sur toi pour te renverser. Tu te relèveras.* » — Prov 24:16",
    "🌿 « *La tristesse du soir fait place à la joie du matin. Tiens bon !* » — Ps 30:6",
    "💚 « *Dieu est notre refuge et notre force, un secours qui ne manque jamais dans la détresse.* » — Ps 46:2",
    "🌊 « *Il ne te laissera pas tomber. Il tient ta main droite.* » — Ps 73:23",
    "☁️ « *Tu souffres aujourd'hui, mais Dieu prépare quelque chose de plus grand pour demain.* » — Rom 8:18",
    "🕊️ « *La paix de Dieu, qui surpasse toute intelligence, gardera vos cœurs.* » — Phil 4:7",
    "🌤️ « *Ce n'est pas la fin. C'est seulement un tournant. Dieu est le Dieu des nouveaux départs.* » — És 43:19",
    "💙 « *L'Éternel t'a vu tomber. Il t'a vu pleurer. Il te relève maintenant.* » — Ps 145:14",
    "🙏 « *Jetez sur lui tous vos soucis, car lui-même prend soin de vous.* » — 1 Pi 5:7",
    "🌻 « *Ne perds pas ta confiance en Dieu, car elle a une grande récompense.* » — Héb 10:35",
    "💜 « *La chute du juste n'est pas définitive. Il se relèvera par la grâce de Dieu.* » — Mic 7:8",
    "🌱 « *L'Éternel rachètera tous tes efforts perdus. Il ne laisse rien en vain.* » — Joël 2:25",
    "🌿 « *Tu es brisé mais pas détruit. Tu es renversé mais pas abattu.* » — 2 Cor 4:9",
    "💚 « *Dieu est le Père des miséricordes et le Dieu de toute consolation.* » — 2 Cor 1:3",
    "🌊 « *Même si tu passes par la vallée de l'ombre de la mort, Il est avec toi.* » — Ps 23:4",
    "☁️ « *Après la tempête, l'arc-en-ciel. Après la défaite, la renaissance.* » — Gen 9:13",
    "🕊️ « *L'Éternel rachète l'âme de ses serviteurs, et tous ceux qui l'espèrent ne seront pas condamnés.* » — Ps 34:23",
    "🌤️ « *Ne te décourage pas dans le bien, car au temps convenable vous moissonnerez si vous ne vous lassez pas.* » — Gal 6:9",
    "💙 « *Il te fortifie et te garde de tout mal. Sa main est sur toi même dans la défaite.* » — 2 Thes 3:3",
    "🙏 « *Je suis venu pour guérir les cœurs brisés. Laisse Jésus guérir le tien.* » — Luc 4:18",
    "💜 « *L'Éternel est lent à la colère et plein de bonté. Il a de la compassion pour toi.* » — Ps 103:8",
    "🌱 « *Il élève le pauvre de la poussière, et le misérable du fumier, pour les faire asseoir avec les princes.* » — Ps 113:7-8",
    "🌿 « *Dieu n'a pas oublié ta douleur. Il a mis tes larmes dans son outre.* » — Ps 56:9",
    "💚 « *Je restaurerai ce qui a été perdu. Je donnerai en échange de la honte une double portion.* » — És 61:7",
    "🌊 « *Même si ton esprit défaille en toi, c'est Dieu qui connaît ton chemin.* » — Ps 142:4",
    "☁️ « *La douleur d'une nuit s'efface à l'aurore. L'Éternel prépare ton matin.* » — Ps 30:6",
    "🕊️ « *Heureux ceux qui pleurent, car ils seront consolés.* » — Matt 5:4",
    "🌤️ « *Ceux qui sèment avec larmes moissonneront avec chants d'allégresse.* » — Ps 126:5",
    "💙 « *Il relève ceux qui sont courbés, il aime les justes.* » — Ps 146:8",
    "🙏 « *L'Éternel se souvient de nous, il bénira. Il fortifiera les petits et les grands.* » — Ps 115:12",
    "🌻 « *Dieu est proche des humbles de cœur. Il ne méprise pas ta douleur.* » — Ps 34:19",
    "💜 « *Après la pluie vient le soleil. Après la défaite vient la leçon qui te mène à la victoire.* » — Ps 19:10",
    "🌱 « *Tous les chemins de l'Éternel sont miséricorde et fidélité pour ceux qui gardent son alliance.* » — Ps 25:10",
    "🌿 « *Tu as été blessé pour être guéri. Tu as chuté pour mieux t'envoler.* » — Os 6:1",
    "💚 « *L'Éternel te rendra le double de ce qui a été pris.* » — Joël 2:25",
    "🌊 « *Il t'a vu dans ta détresse — et il n'a pas détourné son visage. Il a entendu.* » — Ps 22:25",
    "☁️ « *Je t'ai aimé d'un amour éternel. Ta défaite ne change rien à cet amour.* » — Jér 31:3",
    "🕊️ « *Ne pleure pas — Dieu transforme les larmes en perles de victoire future.* » — Apo 21:4",
    "🌤️ « *Fortifiez vos mains languissantes et vos genoux qui chancellent.* » — Héb 12:12",
    "💙 « *La prière sincère du juste est très puissante. Prie après cette défaite.* » — Jac 5:16",
    "🙏 « *Dieu prend soin de toi même dans la défaite. Il n'a pas abandonné son plan pour toi.* » — Jér 29:11",
    "🌿 « *L'Éternel ne laisse pas tomber ses enfants. Il récompense ceux qui persistent.* » — Héb 11:6",
    "💙 « *Ne sois pas abattu car l'Éternel ton Dieu est avec toi partout où tu iras.* » — Jos 1:9",
    "🌸 « *Même si tu trébuchais, tu ne tomberas pas car l'Éternel soutient ta main.* » — Ps 37:24",
    "☀️ « *Après la pluie de cette défaite, l'arc-en-ciel de ta prochaine victoire s'approche.* » — Gen 9:13",
]

# ═══════════════════════════════════════════════════════════════════
#  MAPPING  statut → liste de paroles
# ═══════════════════════════════════════════════════════════════════
_MAP = {
    'gagne_r0': PAROLES_GAGNE_R0,
    'gagne_r1': PAROLES_GAGNE_R1,
    'gagne_r2': PAROLES_GAGNE_R2,
    'gagne_r3': PAROLES_GAGNE_R3,
    'perdu':    PAROLES_PERDU,
}


def get_parole(statut: str, game_number: int = 0, count: int = 5) -> str:
    """
    Retourne un message avec plusieurs versets bibliques pour le statut donné.

    Paramètres
    ----------
    statut      : 'gagne_r0' | 'gagne_r1' | 'gagne_r2' | 'gagne_r3' | 'perdu'
    game_number : numéro du jeu (affiché dans l'en-tête)
    count       : nombre de versets à inclure (défaut 5)

    Retour
    ------
    Texte Markdown prêt à envoyer, à supprimer après 60 secondes.
    """
    key = statut.lower()
    verses = _MAP.get(key, PAROLES_PERDU)

    # Piocher `count` versets uniques (sans répétition)
    nb = min(count, len(verses))
    selected = random.sample(verses, nb)

    # Retirer les références bibliques et les marqueurs italique *
    def strip_ref(v: str) -> str:
        v = re.sub(r'»\s*—\s*[^\n]+$', '»', v)  # » — Ref:X → »
        v = v.replace('*', '')                    # retirer les * d'italique
        return v.rstrip()

    selected = [strip_ref(v) for v in selected]

    prefixes = {
        'gagne_r0': "🏆 **VICTOIRE DIRECTE — La grâce de Dieu !**",
        'gagne_r1': "🌟 **VICTOIRE R1 — La persévérance récompensée !**",
        'gagne_r2': "💪 **VICTOIRE R2 — Deux épreuves, un seul Dieu !**",
        'gagne_r3': "🔥 **VICTOIRE R3 — La foi ultime triomphe !**",
        'perdu':    "🤍 **NE TE DÉCOURAGE PAS — Dieu est encore là !**",
    }
    titre = prefixes.get(key, "🙏 **PAROLE DE DIEU**")

    game_ref = f"_(Jeu **#{game_number}**)_\n" if game_number else ""

    body = "\n\n".join(selected)

    return f"{titre}\n{game_ref}\n{body}{SIGNATURE}"
