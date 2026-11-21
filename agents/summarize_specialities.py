"""Build a small, auditable routing vocabulary and a source-to-category bridge.

No model calls, external dependencies, or source-file mutations. IDs do not depend
on input ordering. Categories describe routing scope, not clinical equivalence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

VERSION = "1.0.0"


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).lower()
    value = value.replace("&", " and ")
    for old, new in {
        "anaesth": "anesth", "paediatr": "pediatr", "peadiatr": "pediatr",
        "orthopaed": "orthoped", "gynaec": "gynec", "gynac": "gynec",
        "haemat": "hemat", "haemato": "hemato", "haemo": "hemo",
        "laproscopic": "laparoscopic", "laprascop": "laparoscop",
        "ophtham": "ophthalm", "opthalm": "ophthalm", "counselling": "counseling",
        "physiothearpy": "physiotherapy", "physiotheraphy": "physiotherapy",
        "gastroentrology": "gastroenterology", "hermatology": "hematology",
        "nepherctomy": "nephrectomy", "translant": "transplant",
        "critaical": "critical", "pulmanology": "pulmonology",
        "venerology": "venereology", "occ uloplasty": "oculoplasty",
        "occuloplasty": "oculoplasty", "ooculoplastics": "oculoplastics",
    }.items():
        value = value.replace(old, new)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def key(value: str) -> str:
    return normalize(value).replace(" ", "")


# id | English label | Chinese label | scope | compact-text regex | superseded IDs
# Explicitly local routing vocabulary: these IDs are NOT SNOMED/UMLS codes.
TAXONOMY_TEXT = r"""
CARDIOLOGY|Cardiology|心脏内科|General cardiac medicine, diagnostics and nonsurgical cardiac care|cardiolog|cardiacscience|cardiaccare|cardiacdiagnostic|cardiactest|heartdisease|heartfailure|^cardiac$|^cardiacdiseases$|cardiovascularcare|bloodpressure|hypertension|hyperlipidaemia|
INTERVENTIONAL_CARDIOLOGY|Interventional Cardiology|介入心脏病学|Coronary angiography, angioplasty, structural interventions and TAVR|interventionalcardiolog|cardiologyinterventional|angioplast|coronaryangiogra|cardiaccatheter|cardiacinvasive|asdvsd|tavr|transradialcardiolog|cardiologythrombolysis|balloonangioplasty|CARDIOLOGY
CARDIAC_ELECTROPHYSIOLOGY|Cardiac Electrophysiology|心脏电生理|Cardiac rhythm disorders, electrophysiology and pacemakers|cardiacelectro|cardiolog.*electrophysiol|arrhythmia|pacemaker|CARDIOLOGY
CARDIAC_SURGERY|Cardiac and Cardiothoracic Surgery|心脏与心胸外科|Cardiac, cardiovascular and cardiothoracic surgery; exclude general thoracic surgery|cardiacsur|cardiacthoracic|cardio(?:thoracic|vascular).*sur|cardiothoracic|cardiovascularthoracic|valvularheartsur|heartvalve|^ctvs$|^cvts$|
VASCULAR_SURGERY|Vascular and Endovascular Surgery|血管与腔内血管外科|Peripheral vascular disease, varicose veins and vascular surgery|vascularsur|vascularandendovascular|vascularendovascular|peripheralvascular|peripheralandendovascular|vascularsciences|vasculardisease|vascularinterventions|varicose|phlebolog|^endovascularsurgery$|
THORACIC_SURGERY|Thoracic Surgery|胸外科|Noncardiac chest and thoracic surgery|^thoracicsur|generalthoracicsur|chestsur|laserlung|thoracicandvascular|vascularandthoracic|
PULMONOLOGY|Pulmonology and Respiratory Medicine|呼吸内科|Lung disease, chest medicine, respiratory failure and pulmonary interventions|pulmon|pulmonary|respiratory|chestmedicine|chestphysician|chestandallergy|tbandchest|tuberculosis|interstitiallung|
SLEEP_MEDICINE|Sleep Medicine|睡眠医学|Sleep disorders, sleep apnea and sleep related airway care|sleepmedicine|sleepdisorder|sleepstudy|sleepapnoea|sleepairway|
ANESTHESIOLOGY|Anesthesiology|麻醉学|General and subspecialty anesthesia and perioperative care|anesth|
CRITICAL_CARE|Critical Care and Intensive Care|重症医学|Adult or unspecified intensive care, ICU and critical care|criticalcare|intensivecare|intensiveandcritical|criticalintensive|intensivist|^icu$|^icuand|^iccc|criticalcoronarycare|
EMERGENCY|Emergency Medicine and Trauma Care|急诊与创伤救治|Emergency medicine, accident care, polytrauma and ambulance services|emergency|accident|^trauma|polytrauma|complextrauma|ambulance|gunshot|disasterresponse|
INTERNAL_MEDICINE|General and Internal Medicine|普通内科与综合内科|General physicians, hospital medicine and adult internal medicine|internalmedicine|generalmedicine|generalphysician|hospitalmedicine|^medicine$|^medicaldepartment$|^physician$|^medicineandcriticalcare$|
FAMILY_MEDICINE|Family Medicine and Primary Care|全科与初级保健|Family medicine, general practice and health checks|familymedicine|familyphysician|familyandgeneral|familyandpreventive|healthcheck|homevisit|
GERIATRICS|Geriatric Medicine|老年医学|General geriatric medicine and older adult care|^geriatrics$|^geriatricmedicine$|^geriatrician$|geriatricinternal|geriatricsinternal|geratricsinternal|oldagecare|geriatriccare|preventivecareforseniors|
ENDOCRINOLOGY|Endocrinology and Metabolic Medicine|内分泌与代谢|Hormonal, thyroid, pituitary, growth and nonsurgical metabolic disorders|endocrinolog|endocrineanddiabetes|metabolicdisorder|metabolicphysician|pituitarydisorder|thyroidhealth|thyroidandparathyroid|growthdisorder|^puberty$|
DIABETOLOGY|Diabetes Care|糖尿病诊疗|Diabetes and diabetology; exclude isolated eye and foot procedures|diabetolog|^diabetes|diabeticcentre|diabeticcentreofexcellence|managementofdiabetes|gestationaldiabetes|
ENDOCRINE_SURGERY|Endocrine Surgery|内分泌外科|Thyroid, parathyroid and other endocrine surgery|endocrinesur|thyroidsur|
GASTROENTEROLOGY|Gastroenterology and Digestive Endoscopy|消化内科与消化内镜|Medical digestive care, GI endoscopy, IBS and acid symptoms|gastroenterolog|gastrolog|gastroscience|gastrointestinalscience|^gastrointestinalendoscopy$|^endoscopy|capsuleendoscopy|^ibs$|gasandacidity|^constipation$|
GI_SURGERY|Gastrointestinal and Hepatopancreatobiliary Surgery|胃肠与肝胆胰外科|GI, foregut, gallbladder, liver, pancreas and HPB surgery|gastrointestin.*sur|gastrosur|surgicalgastro|gastrointestinalandhpb|gastrointestinalandlaparoscop|gastrointestinalandminimally|hepatobiliarysur|hepatobililarysur|hepatopancreatobili.*sur|hepatobiliarypancreatic|hepatopancreatobiliary|hepatobiliarysciences|hepatobiliary|uppergiandforegut|esophagogastric|gastricsur|pancreaticsur|liverandpancreassur|gallstone|gallbladderstone|hpbandgi|^gisurgery$|GASTROENTEROLOGY
HEPATOLOGY|Hepatology|肝病学|Medical liver disease and liver assessment|hepatolog|liverdisease|livercare|acuteliverfailure|fibroscan|billiarysciences|
COLORECTAL|Colorectal Surgery and Proctology|结直肠与肛肠诊疗|Anorectal disorders, hemorrhoids, fissures, fistulas and colorectal surgery|colorectal|coloproctol|proctolog|anorectal|^anal|fistulainano|^piles|haemorrhoid|hemorrhoid|pilonidal|rectalprolapse|pruritusani|
GENERAL_SURGERY|General Surgery|普通外科|General surgery, appendicitis, hernias and unspecified surgery|generalsur|generalandsur|generalandcancersur|appendicit|hernia|^surgery$|postsur|
MINIMALLY_INVASIVE_SURGERY|Laparoscopic and Robotic Surgery|腹腔镜与机器人手术|Unspecified minimally invasive, endoscopic, laparoscopic or robotic surgery; a technique category|laparoscop|lapsrscop|robotic|robotassist|endoscopicsur|minimal.*(?:access|invasive).*sur|minimallyinvasivelasersurgeon|
BARIATRIC_SURGERY|Bariatric and Metabolic Surgery|减重与代谢外科|Bariatric surgery and obesity surgery|bariatric|metabolicsur|obesityanddiabeticsur|
NEPHROLOGY|Nephrology|肾脏内科|Kidney disease, renal failure and nephrology|nephrolog|nephroscience|renalscience|renalcare|kidneyhealth|kidneyscience|renalfailure|nephritic|nephrotic|pediatricrenal|
DIALYSIS|Dialysis|透析|Hemodialysis, dialysis services and dialysis access creation|dialysis|avfistula|NEPHROLOGY
UROLOGY|Urology|泌尿外科|Urinary tract disease, urological surgery, prostate BPH, stones and urodynamics|urolog|urosur|genitourinary|nephrosur|nephrectomy|pyeloplasty|urethr|urinaryincontinence|urodynamic|cystolith|lithotrips|kidneystone|prostatesur|prostatebph|prostatedisease|hydrocele|circumcision|varicocelectomy|femaleurological|
ANDROLOGY|Andrology and Male Fertility|男科学与男性生育|Male infertility, andrology, erectile dysfunction and sperm retrieval|androlog|maleinfertil|malefertil|alphamalefertil|erectiledysfunction|impotenc|^tesa$|spermretrieval|menintimatehealth|
SEXUAL_MEDICINE|Sexual Medicine and Sexology|性医学|Sexology and sexual dysfunction care|sexolog|sexmedicine|sexualmedicine|sexualdisorder|sexclinic|sexualproblem|
OBGYN|Obstetrics and Gynecology|妇产科|General obstetrics, gynecology, pregnancy, contraception and menopause care|gynec|gynocol|obstetri|obsteric|antenatal|postnatal|pregnan|menopause|menstrual|endometriosis|pcos|pcod|polycysticovarian|hysterectomy|colposcopy|ovarianmass|tuboplasty|wellwomen|womenshealth|placentalabruption|lactation|midwifery|familyplanning|^obg$|^obgy$|motherandchild|maternalandchildhealth|
FETAL_MEDICINE|Maternal and Fetal Medicine|母胎医学|Fetal, maternal fetal, foetal and perinatal obstetric medicine|fetal|foetal|fetomaternal|^neonatalperinatal$|OBGYN
REPRODUCTIVE_MEDICINE|Reproductive Medicine and Assisted Reproduction|生殖医学与辅助生殖|Infertility, IVF, IUI, ICSI, embryo procedures and fertility preservation|infertil|fertility|reproductivemedicine|reproductiveendocrinol|reproductivesur|ivf|^iui|^icsi|testtubebaby|eggdonation|blastocyst|oocyte|ovulationinduct|semen|spermfreezing|endometrialreceptivity|laserassistedhatch|preimplant|pgspgd|^pg[ts][am]?$|^pgd$|cryopreservation|OBGYN
UROGYNECOLOGY|Urogynecology and Pelvic Floor Care|泌尿妇科与盆底诊疗|Female pelvic reconstruction, urogynecology and pelvic organ prolapse|urogynec|urogyneac|femalePelvic|femalepelvic|prolapseofthepelvic|pelvichealth|neuropelveol|OBGYN,UROLOGY
PEDIATRICS|Pediatrics and Adolescent Medicine|儿科与青少年医学|General child health, pediatrics and adolescent medicine|pediatr|paedodont|pedodont|adolescen|communitychild|^growth$|^childcare$|
NEONATOLOGY|Neonatology|新生儿科|Newborn care, neonatal medicine and NICU|neonat|neontolog|newbornscreen|nicu|PEDIATRICS
PEDIATRIC_SURGERY|Pediatric and Neonatal Surgery|小儿与新生儿外科|General pediatric and neonatal surgery; organ specific procedures retain their other category|pediatricsur|pediatricsurgery|pediatricand.*sur|pediatricminimallyinvasive|neonatal.*sur|neonatalpediatricsur|PEDIATRICS,NEONATOLOGY,GENERAL_SURGERY,MINIMALLY_INVASIVE_SURGERY
PEDIATRIC_CRITICAL_CARE|Pediatric Critical Care|儿科重症医学|Pediatric critical care, PICU and pediatric intensive care|pediatriccritical|pediatricintensive|pediatricintensiv|picu|CRITICAL_CARE,PEDIATRICS
DEVELOPMENTAL_PEDIATRICS|Developmental Pediatrics and Child Development|发育行为儿科|Child development, developmental disability, autism and special education|developmental|autism|learningdisabil|specialeducation|sensoryintegration|PEDIATRICS
NEUROLOGY|Neurology|神经内科|Medical neurological disease, stroke, epilepsy, movement disorders and neurophysiology|neurolog|neuromedicine|neuroscience|neurovascular|neurodegenerative|neuroimmun|neurophysiol|neuroelectrophysiol|epilep|parkinson|multiplesclerosis|movementdisorder|migraine|headache|brainhaemorrhage|brainhemorrhage|strokecentre|strokemanage|neuromusculardisorder|neuromuscularmedicine|
NEUROSURGERY|Neurosurgery|神经外科|Brain, nerve and cranial neurosurgery|neurosur|neuroendoscop|neuroendovascular|neurointervent|neurotrauma|brain.*sur|skullbasesur|cerebrovascular|neurovascularsur|nerve.*sur|neurolysis|neuronavigat|stereotacticsur|NEUROLOGY
SPINE_SURGERY|Spine Surgery and Spinal Disorders|脊柱外科与脊柱疾病|Spine operations, disc disease and spinal structural conditions|spinesur|spinalsur|spineneurosur|spinalneurosur|spineendoscop|spinecare|spinaldisorder|spineanddeform|slippeddisc|discreplacement|spondyl|vertebroplast|spinalinfection|spinaltubercul|cvjunction|lasertherapypldd|NEUROSURGERY,MINIMALLY_INVASIVE_SURGERY
PSYCHIATRY|Psychiatry|精神科|Mental disorders, psychiatric medicine and psychiatric treatments|psychiatr|psychologicalmedicine|obsessivecompulsive|electroconvuls|^depression$|^anxiety$|anxietyanddepression|mentalhealthandbehav|womenmentalhealth|
ADDICTION|Addiction Medicine|成瘾医学|Substance use, deaddiction, tobacco cessation and addiction medicine|addict|substance|tobaccocessation|smokingmedicine|
PSYCHOLOGY|Psychology, Counseling and Psychotherapy|心理学与心理咨询|Psychology, counseling, psychotherapy and behavioral therapies|psycholog|counsel|psychotherap|stressmanage|familycounsel|grouptherapy|arttherapy|danceandmovement|biofeedback|mentalhealthcounsel|
ORTHOPEDICS|Orthopedics and Musculoskeletal Care|骨科与肌肉骨骼诊疗|Orthopedic medicine and surgery, fractures and structural bone disorders|orthoped|orthogeriatr|boneandjoint|^bone$|avascularnecrosis|fracture|limblength|limbreconstruct|congenitaldeform|osteopor|osteoarthritis|bonegraft|bonemorphogen|periarticular|pelviacetabular|pelvicacetabular|jointdislocation|jointpreserv|jointregener|
JOINT_REPLACEMENT|Joint Replacement and Arthroplasty|关节置换|Hip, knee, shoulder and other joint reconstruction or replacement|jointreplacement|jointandreplacement|arthroplast|hipreplacement|kneereplacement|hipandkneereconstruct|jointreconstruct|shoulderreplacement|elbowjointreplace|totalhipreplace|totalkneereplace|^replacements$|ORTHOPEDICS,MINIMALLY_INVASIVE_SURGERY
ARTHROSCOPY|Arthroscopy and Sports Orthopedics|关节镜与运动骨科|Arthroscopy, sports orthopedic surgery and ligament reconstruction|arthroscop|arthroscrop|ligamentreconstruct|rotatorcuff|ORTHOPEDICS
HAND_SURGERY|Hand and Upper Limb Surgery|手与上肢外科|Hand, wrist, upper limb, brachial plexus and replantation surgery|handsur|handand|handorupper|handtrauma|brachialplexus|upperlimbsur|shoulderandelbow|pollicization|thumbrecreation|limbreplant|
SPORTS_MEDICINE|Sports Medicine|运动医学|Sports injury care and general sports medicine|sportsmedicine|sportmedicine|sportsinjur|sportinjur|sportsinternal|
RHEUMATOLOGY|Rheumatology|风湿免疫科|Arthritis and autoimmune rheumatologic disease|rheumatolog|^arthritis|ankylosing|
ALLERGY_IMMUNOLOGY|Allergy and Clinical Immunology|过敏与临床免疫|Allergy, asthma allergy clinics and clinical immunology; exclude laboratory-only immunology|allerg|^immunolog(?:y|ist)$|clinicalimmunolog|pediatricimmunolog|transplantimmunolog|
INFECTIOUS_DISEASES|Infectious Diseases and Infection Control|感染性疾病与感染控制|Clinical infections, infectious diseases, infection control and vaccination|infectiousdisease|severeinfection|epidemicdisease|infectioncontrol|vaccin|leprosy|
DERMATOLOGY|Dermatology and Cosmetic Dermatology|皮肤科与皮肤美容|Skin, hair and nail disease, dermatologic surgery and aesthetic skin treatments|dermat|^skin|hair|tricholog|acnescar|birthmark|melasma|vitiligo|psoriasis|tattoo|moleremov|nevasremov|keloid|stretchmark|wrinkle|openpores|laserpeel|laserpigment|excessivesweat|nailproblem|cosmetolog|^cosmetics$|
VENEREOLOGY|Venereology|性病学|Sexually transmitted disease and venereology|venere|venereal|
PLASTIC_SURGERY|Plastic, Reconstructive and Aesthetic Surgery|整形修复与美容外科|Plastic reconstruction, aesthetic surgery, microsurgery and craniofacial repair|plasticsur|plasticand|plasticreconstruct|plasticcosmetic|^plastic|^pl astic|reconstructivesur|reconstructionsur|facialplast|facialfeminiz|facereconstruct|nosereconstruct|earreconstruct|rhinoplast|liposuction|tummytuck|breastreduction|gynecomast|gynae?cosmast|scarrevision|genderaffirm|microvascular|microsur|lymph.*microsur|cleft|craniofacial|hemifacial|cancerreconstruct|oncologicreconstruct|aestheticsur|aestheticandcosmeticsur|cosmetic.*sur|flapsur|abbeflap|genitalsur|
BURNS|Burns Care|烧伤诊疗|Burn treatment, burn units and burn surgery|burn|
BREAST_CARE|Breast Care and Breast Surgery|乳腺诊疗与乳腺外科|Breast clinics and nononcology breast surgery; oncology retains separate category|breastcare|breasthealth|breastcentre|breastsur|
WOUND_FOOT_CARE|Wound Care and Podiatry|伤口与足病诊疗|Foot disorders, diabetic foot, wound care and limb salvage|podiatr|podiary|diabeticfoot|woundcare|woundheal|footsur|footandankle|
PAIN_MEDICINE|Pain Medicine|疼痛医学|Pain clinics, nerve blocks, spinal stimulation and pain interventions|painmanage|painmedicine|painclinic|painrelief|chronicpain|painneurolog|paintherapy|palliative.*pain|painandpalliative|painpalliative|painfree|intrathecaldrug|sympatheticnerveblock|transforaminalblock|spinalcordstimul|interventionalpain|backandneckpain|lowbackpain|
PALLIATIVE_CARE|Palliative and Hospice Care|姑息与临终关怀|Palliative medicine, hospice and supportive care|palliat|hospice|
REHABILITATION|Physical Medicine and Rehabilitation|康复医学|Physiatry, neurological rehabilitation and general rehabilitation; exclude dental and vision rehabilitation|rehabilitat|physicalmedicine|spinalcordinjury|braininjurymedicine|regenerativemedicinepmr|neuromuscularmedicinepmr|sportmedicinepmr|sportsmedicinepmr|^divyaang$|
PHYSIOTHERAPY|Physiotherapy|物理治疗|Physical therapy and physiotherapy services|physiotherap|REHABILITATION
OCCUPATIONAL_THERAPY|Occupational Therapy|作业治疗|Occupational therapy, vocational rehabilitation and functional adaptation|occupationaltherap|vocationalrehab|REHABILITATION
PROSTHETICS_ORTHOTICS|Prosthetics and Orthotics|假肢与矫形器|Limb prostheses, orthotics and rehabilitation appliances; exclude dental and ocular prostheses|prostheticorthotic|prostheticsandorthotic|prostheticsorthotic|orthoticsprosthetic|amputee|^prostheticrehabilitation$|^prosthetics$|REHABILITATION
NUTRITION|Nutrition and Dietetics|营养与膳食|Dietitians, clinical nutrition, nutritional counseling and nonsurgical weight management|nutrit|dietiti|dietici|dietetic|dietitic|^dietics$|^dietand|weightmanage|weightloss|^obesity$|obesityweightloss|
ENT|Otolaryngology (ENT)|耳鼻喉科|Ear, nose, throat, head and neck surgery, otology and rhinology|^ent|pediatricent|otorhino|otolaryng|otolog|neurotolog|earno[ s]?ethroat|earnosethroat|earwax|laryngolog|rhinolog|headandnecksur|headnecksur|tinnitus|parotidmass|salivaryglandsur|tonguetie|
AUDIOLOGY|Audiology and Hearing Rehabilitation|听力学与听觉康复|Hearing tests, audiometry and cochlear implant rehabilitation|audiolog|audiometr|cochlearimplant|vestibularrehab|REHABILITATION
SPEECH_THERAPY|Speech, Language and Swallowing Therapy|言语语言与吞咽治疗|Speech pathology, voice, fluency and swallowing therapy|speech|languagetherap|voice|fluency|stutter|articulationtherap|dysphonia|swallow|oralmotricity|REHABILITATION
OPHTHALMOLOGY|General Ophthalmology|综合眼科|General eye examinations, eye care and ophthalmology|ophthalm|ophthalmolog|eyecare|eyecheck|eyeexam|eyehospital|eyesurgeon|eyetrauma|
CATARACT|Cataract and Lens Surgery|白内障与晶状体手术|Cataract, phacoemulsification and lens implantation|cataract|phacosur|OPHTHALMOLOGY
GLAUCOMA|Glaucoma|青光眼|Glaucoma assessment and treatment|glaucoma|OPHTHALMOLOGY
RETINA|Retina and Vitreoretinal Care|视网膜与玻璃体视网膜诊疗|Retinal disease, diabetic retinopathy, macula, ROP and vitreoretinal surgery|retina|retino|vitreo|vitrectom|macular|macularedema|epiretinal|diabeticeye|intravitreal|^rop$|armd|OPHTHALMOLOGY
CORNEA|Cornea, Ocular Surface and Uveitis|角膜眼表与葡萄膜炎|Corneal disease and transplantation, keratoplasty, dry eye, uveitis and ocular inflammation|cornea|keratocon|keratoplast|limbalstem|dryeye|uvea|uveitis|ocularinflamm|ocularimmunol|pterygium|pinguecula|OPHTHALMOLOGY
REFRACTIVE_SURGERY|Refractive Surgery|屈光手术|LASIK, PRK, ICL and refractive laser surgery; exclude nonsurgical refractive errors|lasik|contoura|contura|refractivesur|refractivelaser|prksur|photorefractive|^icl|implantablecontacts|visioncorrection|smilepro|OPHTHALMOLOGY
STRABISMUS|Strabismus and Orthoptics|斜视与双眼视觉|Squint, strabismus, orthoptics, amblyopia and binocular vision|squint|strabismus|orthoptic|binocular|lazyeye|OPHTHALMOLOGY
OCULOPLASTICS|Oculoplastics, Orbit and Ocular Prosthetics|眼整形眼眶与义眼|Eyelid, orbit, lacrimal and ocular prosthetic care|oculoplast|ophthalmicplastic|ocularprosthe|eyeprosthe|lacrimal|ptosis|chalazion|OPHTHALMOLOGY,PLASTIC_SURGERY
OPTOMETRY_LOW_VISION|Optometry, Contact Lenses and Vision Rehabilitation|视光隐形眼镜与低视力康复|Refraction, myopia, contact lenses, vision testing and low vision care|optometr|optical|contactlens|contactlenses|lowvision|visionrehab|visionenhance|visiontherap|visualfield|visualelectro|computervision|digitaleyestrain|refractiveerror|myopia|OPHTHALMOLOGY,REHABILITATION
EYE_BANK|Eye Banking|眼库|Eye bank and eye tissue services|eyebank|
DENTISTRY|General Dentistry|综合牙科|General dental consultation and unspecified dental services|dentist|dentistr|^dental|oralhealth|familydent|^ddentistry$|
ORTHODONTICS|Orthodontics and Dentofacial Orthopedics|正畸与牙颌矫形|Braces, aligners, Invisalign and dentofacial orthodontics|orthodont|dentofacialorthoped|braces|aligner|invisalign|teethstraighten|malalignedteeth|jaworthoped|DENTISTRY,ORTHOPEDICS
ENDODONTICS|Endodontics and Conservative Dentistry|牙髓病与牙体修复|Root canals, endodontics, conservative dentistry, caries and fillings|endodont|rootcanal|rootcanals|conservativedent|conservativeand|^conservatives$|filling|cavity|brokentooth|toothcolour|DENTISTRY
PERIODONTICS|Periodontics and Dental Prevention|牙周与牙科预防|Gum disease, scaling, polishing, periodontal surgery, prophylaxis and sealants|periodont|peridont|periondont|gum|scaling|polish|rootplan|crownlengthen|softtissuegraft|fluoride|sealant|oralprophylaxis|preventive.*dent|preventivedental|publichealthdent|communitydent|DENTISTRY,PLASTIC_SURGERY
PROSTHODONTICS|Prosthodontics and Dental Prostheses|口腔修复与义齿|Dentures, dental crowns, bridges, prosthetic dentistry and full mouth rehabilitation|prosthodont|prosthodonto|denture|crowns?|bridges?|implantprosthe|prostheticdent|teethreplace|inlaysandonlays|maxillofacialprosthe|maxillofacialprosthod|fullmouth|DENTISTRY,REHABILITATION
DENTAL_IMPLANTS|Dental Implantology|口腔种植|Dental implants, implant dentistry and oral implantology; unqualified implants require review|implantolog|implantalog|implantdent|dentalimplant|miniimplant|computer.*implantsur|allon46implant|oralimplant|DENTISTRY
PEDIATRIC_DENTISTRY|Pediatric Dentistry|儿童牙科|Pediatric dentistry, pedodontics and child dental care|pedodont|paedodont|child.*dent|pediatric.*dent|pediatricrootcanal|pediatricendodont|pediatricsandpreventivedent|DENTISTRY,PEDIATRICS
COSMETIC_DENTISTRY|Cosmetic and Aesthetic Dentistry|牙齿美容|Dental veneers, whitening, bonding, cosmetic dentistry and smile design|cosmetic.*dent|cosmeticsdent|aestheticdent|estheticdent|dentalaesthetic|dentalcosmetic|dentalveneer|veneers|laminate|whiten|bleach|smiledesign|smilecorrect|digitalsmile|dentaljewell|cosmeticbond|^smile$|DENTISTRY
ORAL_MAXILLOFACIAL_SURGERY|Oral and Maxillofacial Surgery|口腔颌面外科|Oral surgery, tooth extraction, jaw surgery and maxillofacial trauma|maxillofacial|faciomaxill|fasciomaxill|maxillofacial|oromaxillo|oralsur|oralanddentalsur|dentoalveol|toothextract|wisdomtooth|impactedtooth|impactiontooth|orthognath|distractionosteogen|facialfracture|maxillafracture|facialasymmetr|facialtrauma|dentalomfs|dentalandoralsur|dentalandmaxillo|palatesur|DENTISTRY,PLASTIC_SURGERY
ORAL_MEDICINE|Oral Medicine and Orofacial Pain|口腔内科与口面疼痛|Oral mucosal disease, oral medicine and temporomandibular disorders|oralmedicine|oraldiagnos|orofacialpain|oralsubmuc|temporomandibular|tmj|tmjoint|PAIN_MEDICINE,DENTISTRY
ORAL_RADIOLOGY|Dental and Maxillofacial Radiology|口腔颌面影像|Dental imaging, CBCT and oral/maxillofacial radiology|dentalimag|dentalradiol|dentalxray|dentalmaxillofacialradiol|oral.*radiolog|^cbct$|RADIOLOGY,DENTISTRY,ORAL_MAXILLOFACIAL_SURGERY
ORAL_PATHOLOGY|Oral and Maxillofacial Pathology|口腔颌面病理|Oral pathology, oral histology, oral biopsy and forensic odontology|oral.*patholog|oralhistolog|oralbiopsy|PATHOLOGY,DENTISTRY,ORAL_MAXILLOFACIAL_SURGERY,MICROBIOLOGY
DENTAL_SEDATION|Dental Anesthesia and Sedation|牙科麻醉与镇静|Dental anesthesia, sedation dentistry and anxious patient sedation|dentalanesth|dentalsedat|sedationdent|sedationfornervous|sleepdent|sleepingdent|hypnodont|ANESTHESIOLOGY,DENTISTRY
ONCOLOGY|General Oncology and Cancer Care|综合肿瘤诊疗|Unspecified oncology, cancer diagnosis, screening, staging and cancer services|oncolog|oncocare|cancercare|cancerdiagnos|cancerscreen|cancerstag|solidmalignan|cancerreconstr|
MEDICAL_ONCOLOGY|Medical Oncology and Systemic Therapy|肿瘤内科与全身治疗|Medical oncology, chemotherapy, targeted therapy, CAR T and immunotherapy|medicaloncolog|chemotherap|targetedtherap|cartcell|immunotherap|ONCOLOGY
SURGICAL_ONCOLOGY|Surgical Oncology|肿瘤外科|Cancer surgery and surgical oncology; organ specific sites retained in source text|surgicaloncolog|oncosur|cancersur|cancer.*sur|cancersurgery|oncologysur|oncologist.*sur|carcinoma|^camaxilla$|^cathyroid$|sarcoma|hipec|pipac|peritonealsurface|ONCOLOGY,GENERAL_SURGERY
RADIATION_ONCOLOGY|Radiation Oncology and Radiotherapy|放射肿瘤学与放疗|Radiation oncology, radiotherapy and radiosurgery|radiationoncol|radiotherap|radiationtherap|radiationsur|radiosur|ONCOLOGY
HEMATOLOGY|Hematology and Hemato Oncology|血液科与血液肿瘤|Clinical blood disorders, hematology and hematologic oncology; exclude isolated blood banking|hematolog|hematooncol|hematoncol|blooddisease|ONCOLOGY
STEM_CELL_TRANSPLANT|Bone Marrow and Hematopoietic Stem Cell Transplant|骨髓与造血干细胞移植|Bone marrow transplantation and hematopoietic stem cell transplant; unspecified stem cells require review|bonemarrowtrans|hematopoieticstem|stemcelltransplant|bmt|HEMATOLOGY
ORGAN_TRANSPLANT|Solid Organ Transplantation|实体器官移植|Kidney, liver, heart, lung, pancreas and multi organ transplantation|kidneytransplant|renaltransplant|livertransplant|hearttransplant|lungtransplant|heartandlungtransplant|pancreastransplant|pancreatictransplant|organtransplant|organtransplantation|transplantsur|visceralandabdominal|
PATHOLOGY|Pathology and Laboratory Medicine|病理与检验医学|Pathology, clinical laboratory services, biopsies and unspecified laboratory diagnostics|patholog|^labmedicine$|laboratory|^lab(?:oratory)?$|cytolog|cytopath|histocyt|histopath|coagulat|diagnosisandbiopsy|flowcytomet|organTest|organtesting|
BIOCHEMISTRY|Clinical Biochemistry|临床生物化学|Clinical chemistry, hormone assays and biochemical testing|biochem|clinicalchem|hormonalassay|hormonelaboratory|immunoassay|^hormones$|^rfttest$|PATHOLOGY
MICROBIOLOGY|Microbiology and Infectious Disease Laboratory|微生物检验|Microbiology, bacteriology, mycology, virology, parasitology and serology|microbiolog|bacteriol|mycolog|virolog|parasitol|serolog|PATHOLOGY
IMMUNOLOGY_LAB|Immunology Laboratory|免疫学检验|Laboratory immunology, autoimmunity testing and immunopathology|immunologylab|immunologyandautoimmunitylab|immunopathol|PATHOLOGY
GENETICS|Genetics, Genomics and Molecular Diagnostics|遗传基因组与分子诊断|Genetics, genetic counseling, cytogenetics, karyotyping and molecular testing|genetic|genomic|cytogen|karyotyp|dnase[x]?ing|molecular|pcrtest|PATHOLOGY
TRANSFUSION|Transfusion Medicine and Blood Banking|输血医学与血库|Blood banks, blood storage, immunohematology and transfusion medicine|transfusion|bloodbank|bloodcentre|bloodstorage|immunohematolog|HEMATOLOGY,PATHOLOGY
RADIOLOGY|Radiology and Diagnostic Imaging|放射与诊断影像|Diagnostic radiology, X ray, ultrasound, CT and noninterventional imaging|radiolog|radiodiagnos|clinicalimag|imagingtest|neuroimag|xray|sonogra|sonology|ultrasound|ultrasonolog|doppler|mammogra|breastimag|fetal.*scans|featscans|^hsg$|^dexa$|^radiodiagnostics$|
INTERVENTIONAL_RADIOLOGY|Interventional Radiology|介入放射学|Image guided interventions and interventional radiology|interventionalradiolog|interventionalneuroradiolog|neuroradiolog.*interven|vascularandinterventionalradiolog|imageguidedinterven|imaginginterventional|interventionaloncolog|RADIOLOGY
NUCLEAR_MEDICINE|Nuclear Medicine|核医学|Nuclear imaging, nuclear therapy and theranostics|nuclearmedicine|nucleartherap|lu177|psmatherap|
AYURVEDA|Ayurveda|阿育吠陀|Ayurvedic systems and named Ayurvedic clinical disciplines|ayurved|panchakarma|panchkarma|kayachikitsa|kaumarabhritya|koumarbhritya|kriyasari|rachanasari|prasooth|prasutitantra|swasthavrit|shalya|shalakya|salakya|roganidan|chikitsa|
HOMEOPATHY|Homeopathy|顺势疗法|Homeopathic and homoeopathic services|homeopath|homoeopath|
INTEGRATIVE_MEDICINE|Integrative, Complementary and Alternative Medicine|整合与补充替代医学|Alternative, holistic and integrated medicine; yoga and naturopathy|alternativemed|alternativesystem|holisticmed|holistictherap|integrat|naturopath|yoga|acupress|chromotherap|magnetotherap|ozonetherap|bowentechnique|oestopath|
PUBLIC_OCCUPATIONAL_HEALTH|Public, Preventive and Occupational Health|公共预防与职业卫生|Public health, epidemiology, occupational medicine and health prevention|publichealth|communityhealth|communitymedicine|communityandpublichealth|preventivemed|occupationalhealth|occupationalandenviron|environmentalandoccupation|industrialhygiene|epidemiolog|globalhealth|preventiveandcommunity|chronicdiseaseprevent|lifestyledisease|
TOXICOLOGY|Toxicology and Forensic Medicine|毒理与法医学|Poisoning, snake bite, toxicology and forensic medicine|toxicolog|toxicopath|snakebite|poisoning|forensicmedicine|
SPECIAL_MEDICINE|Aerospace, Hyperbaric and Special Environment Medicine|航空航天与高压特殊环境医学|Aerospace medicine and undersea/hyperbaric medicine|aerospacemed|underseaandhyperbaric|
RESEARCH_SCIENCES|Medical Research and Basic Sciences|医学研究与基础学科|Anatomy, physiology, research, informatics, medical physics and biostatistics|^anatomy$|generalanatomy|^physiology$|biostat|datascience|clinicalresearch|translational|clinicalinformat|medicalphysics|precisionmedicine|
PHARMACY|Pharmacy and Clinical Pharmacology|药学与临床药理|Pharmacy, pharmacology and drug monitoring|pharmac|therapeuticdrugmonitor|
SUPPORT_SERVICES|Hospital Support and General Services|医院支持与综合服务|Non specialty operations, outpatient services, home care and unspecified diagnostics|administration|engineering|maintenance|healthcaretourism|homecare|homecollection|outpatient|nursing|^diagnostics$|^diagnostictesting$|^24hrsdiagnostics$|^specialistconsultation$|highendtesting|threedimensionalscanners|dentallab|
UNSPECIFIED|Unspecified or Multi Specialty|未指明与多专科|Generic other, all and multi specialty entries without named clinical domains|^allsp[ecia]+lities$|^allspecialities$|^multispeciality$|^superspeciality$|^otherspecialties$|^otherdiseases$|^independentdivisions$|
UNRESOLVED|Unresolved or Ambiguous|未解析或含义不明|Insufficient, malformed or ambiguous source text; exclude from automatic routing|(?!)|
"""


def taxonomy() -> dict:
    result = {}
    # Patterns contain |, so parse first four columns and the final suppression column.
    for line in TAXONOMY_TEXT.strip().splitlines():
        code, name, zh, scope, rest = line.split("|", 4)
        pattern, suppress = rest.rsplit("|", 1)
        result[code] = dict(speciality_id="SP_" + code, speciality_name=name,
                            speciality_name_zh=zh, scope=scope, pattern=pattern,
                            suppress=suppress.split(",") if suppress else [])
    return result


# Whole-entry corrections/decisions. None means deliberately unresolved.
# Broad procedure words without a body site must not silently become dental/eye care.
OVERRIDES = {
    "angiogram": None, "electrophysiology": None, "implant": None,
    "implants": None, "implantServices": None, "prosthesis": None,
    "PRP": None, "PRP Therapy": None, "PRPTherapy": None,
    "regenerativeMedicine": None, "stemCellTherapy": None,
    "stemCellPreservation": None, "stemCellBanking": None,
    "Stem Cell Regreneration & Cartilage repair": ["ORTHOPEDICS"],
    "stemCellTransplant": ["STEM_CELL_TRANSPLANT"],
    "Stem Cell Transplant": ["STEM_CELL_TRANSPLANT"],
    "Stem Cell Transplantation": ["STEM_CELL_TRANSPLANT"],
    "bone marrow translant": ["STEM_CELL_TRANSPLANT"],
    "Stones": None, "prophylaxis": None, "flapSurgery": None,
    "Flap Surgery": None, "facial": None, "facial aesthetics": ["PLASTIC_SURGERY"],
    "facialGrowthGuidance": ["ORTHODONTICS"],
    "lasers": None, "laserSurgery": None, "laserTreatments": None,
    "radiofrequencyAblation": None, "interventional": None,
    "inflammatoryDiseases": None, "hormonalTherapy": None,
    "Oestopathy": None, "ketamineInfusionTherapy": None,
    "neuromodulation": None, "nerveInjury": None,
    "silk": None, "smile": None, "smilePro": ["REFRACTIVE_SURGERY"],
    "Whipple Specimen": ["PATHOLOGY"], "biostatisticsAndDataScience": ["RESEARCH_SCIENCES"],
    "orth orthopedic? wrong": None,
    ' {"dentistry":"dentistry"}': ["DENTISTRY"],
    '{"dentistry":"dentistry"}': ["DENTISTRY"],
    "acrylicPartialDenture": ["PROSTHODONTICS"],
    "All on 4/6 implant": ["DENTAL_IMPLANTS"],
    "laserLipSurgery": ["PLASTIC_SURGERY"],
    "soft tissue sarcoma surgeries": ["SURGICAL_ONCOLOGY"],
    "anaplastology": ["PROSTHETICS_ORTHOTICS"],
    "acuteCareSurgery": ["GENERAL_SURGERY"],
    "Bone Tumor Treatment": ["ONCOLOGY", "ORTHOPEDICS"],
    "Nerve Tumor Treatment": ["ONCOLOGY", "NEUROSURGERY"],
    "Scalp Tumor": ["ONCOLOGY"],
    "botoxTherapy": None,
    "Care/risk management of adult asthma": ["PULMONOLOGY"],
    "echocardiography": ["CARDIOLOGY"],
    "gingivoplasty": ["PERIODONTICS"],
    "hipPreservation": ["ORTHOPEDICS"],
    "Knee Surgery": ["ORTHOPEDICS"],
    "kneeSurgery": ["ORTHOPEDICS"],
    "laserEyeSurgeries": ["OPHTHALMOLOGY"],
    "laserEyeSurgery": ["OPHTHALMOLOGY"],
    "Lymphedema": ["VASCULAR_SURGERY"],
    "Magnet Therapy": ["INTEGRATIVE_MEDICINE"],
    "Mastectomy in Breast Cancer": ["SURGICAL_ONCOLOGY", "BREAST_CARE"],
    "microbialKeratitis": ["CORNEA"],
    "miscarriageClinic": ["OBGYN"],
    "myocardialInfarction": ["CARDIOLOGY"],
    "oralAndMaxilloSurgery": ["ORAL_MAXILLOFACIAL_SURGERY"],
    "peripheralAngiography": ["VASCULAR_SURGERY"],
    "socialAndBehavioralSciences": ["RESEARCH_SCIENCES"],
    "Teeth Cleaning": ["PERIODONTICS"],
    "telemedicine": ["SUPPORT_SERVICES"],
    "thoracicMedicine": ["PULMONOLOGY"],
    "thoracicSyndrome": None,
    "unaniHospitals": ["INTEGRATIVE_MEDICINE"],
    "uroOncoTreatment": ["UROLOGY", "ONCOLOGY"],
    "tumorMarker": ["PATHOLOGY"],
    "cancerMarker": ["PATHOLOGY"],
    "epilepsySurgery": ["NEUROSURGERY"],
    "gynecomastia": ["PLASTIC_SURGERY"],
    "Gynaecosmastia": ["PLASTIC_SURGERY"],
    "Crown Lengthening": ["PERIODONTICS"],
    "nuclearMedicineAndMolecularImaging": ["NUCLEAR_MEDICINE"],
    "fetalPrenatalEcoCardiography": ["FETAL_MEDICINE", "CARDIOLOGY"],
    "Ca Maxilla": ["ONCOLOGY"],
    "Ca Thyroid": ["ONCOLOGY"],
    "Verrucous Carcinoma": ["ONCOLOGY"],
    "Laparoscopic Kidney Surgery": ["UROLOGY"],
    "Kids Dentistry": ["PEDIATRIC_DENTISTRY"],
    "isolationICU": ["CRITICAL_CARE"],
    "Non-Interventional Cardiology": ["CARDIOLOGY"],
    "Care/risk management of pediatric asthma": ["PULMONOLOGY"],
    "pediatricEndoscopy": ["GASTROENTEROLOGY"],
    "pediatricsSurgery": ["PEDIATRIC_SURGERY"],
    "pediatricThoracicSurgery": ["THORACIC_SURGERY"],
    "pediatricTrauma": ["EMERGENCY"],
    "pediatricSST": None,
    "pediatricCardiacCentre": ["CARDIOLOGY"],
    "pediatricCardiacServices": ["CARDIOLOGY"],
    "paediatricCardiacCentre": ["CARDIOLOGY"],
    "CARDIOLOGY & ENT": ["CARDIOLOGY", "ENT"],
    "generalMedicineAndICU": ["INTERNAL_MEDICINE", "CRITICAL_CARE"],
    "headAndNeckOncologicSurgery": ["SURGICAL_ONCOLOGY"],
    "Gastrointestinal & Hepatobiliary Oncology": ["ONCOLOGY"],
    "Ankylosing Spondylitis": ["RHEUMATOLOGY"],
    "facialFractureTreatment": ["ORAL_MAXILLOFACIAL_SURGERY"],
    "maxillaFractureTreatment": ["ORAL_MAXILLOFACIAL_SURGERY"],
    "Dental Lab": ["SUPPORT_SERVICES"],
    "psychologicalMedicine": ["PSYCHIATRY"],
    "highRiskPregnancyAndInfertility": ["OBGYN", "REPRODUCTIVE_MEDICINE"],
    "Abbe Flap Ca Lip": ["PLASTIC_SURGERY", "ONCOLOGY"],
    "uroOncology": ["UROLOGY", "ONCOLOGY"],
    "Uro-Oncology": ["UROLOGY", "ONCOLOGY"],
    "andrologyAndUroOncology": ["ANDROLOGY", "UROLOGY", "ONCOLOGY"],
    "Cryopreservation": None,
}


def classify(raw: str, cats: dict) -> tuple[list[str], str, str]:
    if raw in OVERRIDES:
        codes = OVERRIDES[raw]
        return (codes or ["UNRESOLVED"], "curated_exception",
                "ambiguous_or_malformed" if codes is None else "curated_routing")
    compact = key(raw)
    normalized = normalize(raw)
    hits = set()
    for code, cat in cats.items():
        searchable = compact
        # Guard against English substrings that cross clinical/morpheme boundaries.
        if code == "UROLOGY":
            searchable = re.sub(r"neurolog|neurosur", "neuro", searchable)
        elif code == "PEDIATRIC_CRITICAL_CARE":
            searchable = searchable.replace("picu", "")
            if re.search(r"\bpicu\b", normalized):
                hits.add(code)
        elif code == "ANDROLOGY":
            searchable = searchable.replace("female", "woman")
        elif code == "GENETICS":
            searchable = searchable.replace("morphogenetic", "morphogenic")
        elif code == "DENTISTRY":
            searchable = searchable.replace("behavioralhealth", "behaviorhealth")
        elif code == "INTEGRATIVE_MEDICINE":
            searchable = searchable.replace("sensoryintegration", "sensory")
        elif code == "ORGAN_TRANSPLANT":
            searchable = re.sub(r"(?:hair|corneal)transplantsur", "tissuesur", searchable)
        elif code == "PATHOLOGY":
            searchable = searchable.replace("speechpathology", "speechtherapy")
        elif code == "NEONATOLOGY":
            searchable = searchable.replace("nicu", "")
            if re.search(r"\bnicu\b", normalized):
                hits.add(code)
        elif code == "FETAL_MEDICINE":
            searchable = searchable.replace("neonatalperinatal", "neonatal")
        if re.search(cat["pattern"], searchable):
            hits.add(code)
    # Cancer site words alone identify oncology, not a particular treatment modality.
    if re.search(r"cancer|oncolog|oncosur|onco(?:care|treatment)", compact) and not re.search(
        r"(?:cancermarker|tumormarker|cancerregistry|cancervaccin)", compact
    ):
        hits.add("ONCOLOGY")
    # Use the more specific scope when general and specific rules match the same phrase.
    suppressed = {parent for code in hits for parent in cats[code]["suppress"]}
    hits -= suppressed
    if "NEUROSURGERY" in hits and re.search(r"\bneurology\b", normalized):
        hits.add("NEUROLOGY")
    # Technique alone is useful only when no organ/service-specific surgical group exists.
    if len(hits) > 1:
        hits.discard("MINIMALLY_INVASIVE_SURGERY")
    # General pediatrics is an age facet when an organ-specific service is present.
    if len(hits) > 1:
        hits.discard("PEDIATRICS")
    # A dental/eye/skin compound is not automatically general cancer care or general surgery.
    if any(c in hits for c in ("ORAL_RADIOLOGY", "ORAL_PATHOLOGY")):
        hits.discard("ORAL_MEDICINE")
    # Distinguish peripheral vascular surgery from neurovascular and cardiac terms.
    if re.search(r"(?:neurovascular|vascularneuro|cerebrovascular)", compact):
        hits.discard("VASCULAR_SURGERY")
    if "NEUROSURGERY" in hits and "neuroendovascular" in compact:
        hits.discard("VASCULAR_SURGERY")
    if "CARDIAC_SURGERY" in hits and "cardiothoracicradiology" in compact:
        hits.discard("CARDIAC_SURGERY")
    if "VASCULAR_SURGERY" in hits and "microvascular" in compact:
        hits.discard("VASCULAR_SURGERY")
    if "PLASTIC_SURGERY" in hits and any(c in hits for c in (
        "JOINT_REPLACEMENT", "UROGYNECOLOGY", "PROSTHODONTICS", "ORAL_MAXILLOFACIAL_SURGERY"
    )) and not re.search(r"plastic|aesthetic|cosmetic|cleft", compact):
        hits.discard("PLASTIC_SURGERY")
    if "ORAL_MAXILLOFACIAL_SURGERY" in hits and "PROSTHODONTICS" in hits and "surgery" not in compact:
        hits.discard("ORAL_MAXILLOFACIAL_SURGERY")
    if "CARDIAC_SURGERY" in hits and "THORACIC_SURGERY" in hits:
        hits.discard("THORACIC_SURGERY")
    if "PERIODONTICS" in hits:
        hits.discard("PUBLIC_OCCUPATIONAL_HEALTH")
    if "GENETICS" in hits and "counsel" in compact:
        hits.discard("PSYCHOLOGY")
    if "NUTRITION" in hits and "counsel" in compact and "psycholog" not in compact:
        hits.discard("PSYCHOLOGY")
    if "GERIATRICS" in hits:
        hits.discard("INTERNAL_MEDICINE")
    if "DENTISTRY" in hits and "painfree" in compact:
        hits.discard("PAIN_MEDICINE")
    if "NEONATOLOGY" in hits and re.search(r"neonatal.*(?:critical|intensive)", compact):
        hits.discard("CRITICAL_CARE")
    if "REPRODUCTIVE_MEDICINE" in hits and "ANDROLOGY" in hits and not (
        "female" in compact or "ivf" in compact or "iui" in compact or "icsi" in compact
    ):
        hits.discard("REPRODUCTIVE_MEDICINE")
    if "SPINE_SURGERY" in hits and "spinaltuberculosis" in compact:
        hits.discard("PULMONOLOGY")
        hits.add("INFECTIOUS_DISEASES")
    if "CARDIAC_SURGERY" in hits and not re.search(r"(?:andvascular|vascularand|thoracicvascular)", compact):
        hits.discard("VASCULAR_SURGERY")
    # Reproductive endocrinology/infertility is not a generic endocrine disease service.
    if compact.startswith("reproductiveendocrinology"):
        hits.discard("ENDOCRINOLOGY")
    # Laboratory subdomains are different from their clinical counterparts.
    if re.search(r"hematology(?:laboratory|automation)|hematopathology", compact):
        hits.discard("HEMATOLOGY")
        hits.add("PATHOLOGY")
    if not hits:
        return ["UNRESOLVED"], "no_rule", "no_supported_category"
    return sorted(hits), "lexical_rule", "routing_rule"


def age_scope(raw: str) -> str:
    compact = key(raw)
    if "adultandpediatric" in compact:
        return "adult_and_pediatric"
    if re.search(r"neonat|newborn|nicu", compact):
        return "neonatal_and_pediatric" if re.search(r"pediatr|picu", compact) else "neonatal"
    if re.search(r"pediatr|paedodont|pedodont|child|kids", compact):
        return "pediatric"
    if re.search(r"adolescen", compact):
        return "adolescent"
    if re.search(r"geriatr|geratr|elderly|oldage|senior", compact):
        return "geriatric"
    return "adult" if "adult" in compact else "unspecified"


def build(raw_values: list[str]) -> tuple[list[dict], list[dict], dict]:
    if not isinstance(raw_values, list) or not all(isinstance(v, str) and v.strip() for v in raw_values):
        raise ValueError("Input must be a JSON array of nonempty strings")
    cats = taxonomy()
    members = {c: [] for c in cats}
    mapping = []
    for raw in dict.fromkeys(raw_values):
        codes, method, reason = classify(raw, cats)
        source_id = "SRC_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        normalized = normalize(raw)
        # Recover a serialized dictionary value, without altering the exact source join key.
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = None
        malformed = isinstance(parsed, dict) or "? wrong" in raw
        review = codes == ["UNRESOLVED"] or malformed or "UNSPECIFIED" in codes
        if "STEM_CELL_TRANSPLANT" in codes and "stemcell" in key(raw) and "hematopoietic" not in key(raw):
            review = True
            reason = "stem_cell_type_unspecified"
        for code in codes:
            # Only exact normalized category labels are called equivalent.
            relation = "equivalent_label" if normalized == normalize(cats[code]["speciality_name"]) else "routing_membership"
            if code == "UNRESOLVED":
                relation = "unresolved"
            mapping.append(dict(
                source_id=source_id, raw_speciality=raw, normalized_speciality=normalized,
                normalized_key=key(raw), speciality_id=cats[code]["speciality_id"],
                mapping_relation=relation, mapping_method=method, age_scope=age_scope(raw),
                is_multi_category=len(codes) > 1, needs_review=review,
                review_reason="serialized_object_in_string" if malformed and isinstance(parsed, dict) else
                              (reason if review else ""),
                rule_id=code, taxonomy_version=VERSION,
            ))
            members[code].append(raw)
    counts = Counter(row["source_id"] for row in mapping)
    summary = []
    for code, cat in cats.items():
        values = members[code]
        if not values:
            continue
        rows = [r for r in mapping if r["speciality_id"] == cat["speciality_id"]]
        summary.append(dict(
            speciality_id=cat["speciality_id"], speciality_name=cat["speciality_name"],
            speciality_name_zh=cat["speciality_name_zh"], scope=cat["scope"],
            source_entry_count=len(values), needs_review_count=sum(r["needs_review"] for r in rows),
            examples=sorted(values, key=lambda v: (len(v), v.casefold()))[:4],
            routable=code not in {"UNRESOLVED", "UNSPECIFIED"}, taxonomy_version=VERSION,
        ))
    summary.sort(key=lambda r: r["speciality_id"])
    mapping.sort(key=lambda r: (r["raw_speciality"].casefold(), r["raw_speciality"], r["speciality_id"]))
    report = dict(input_rows=len(raw_values), unique_source_entries=len(counts),
                  summary_rows=len(summary), mapping_rows=len(mapping),
                  multi_category_sources=sum(n > 1 for n in counts.values()),
                  review_sources=len({r["source_id"] for r in mapping if r["needs_review"]}),
                  unresolved_sources=len(members["UNRESOLVED"]),
                  agent_row_reduction_pct=round((1-len(summary)/len(counts))*100, 2) if counts else 0)
    assert len(counts) == len(set(raw_values))
    assert len({r["source_id"] for r in mapping}) == len(set(raw_values))
    assert all(r["speciality_id"] in {s["speciality_id"] for s in summary} for r in mapping)
    assert len({(r["source_id"], r["speciality_id"]) for r in mapping}) == len(mapping)
    return summary, mapping, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("raw_specialties.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    args = parser.parse_args()
    summary, mapping, report = build(json.loads(args.input.read_text(encoding="utf-8")))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("specialities_summarize", summary), ("specialities_mapping", mapping)):
        (args.output_dir / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
