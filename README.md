Version forked from [Gitlab](https://gitlab.com/scripta/escriptorium/)
The docker-compose.yml file has been modified based on this [issue](https://gitlab.com/scripta/escriptorium/-/issues/1139) on Gitlab.

eScriptorium is part of the [Scripta](https://www.psl.eu/en/scripta), [RESILIENCE](https://www.resilience-ri.eu) and [Biblissima+](https://projet.biblissima.fr/) projects, and has received funding from Université PSL and from The European Union's [Horizon 2020 Research and Innovation Programme](https://ec.europa.eu/programmes/horizon2020/en/what-horizon-2020) under Grant Agreement no. 871127, from the Programme d'investissements d'avenir of the [Agence Nationale de Recheche](https://anr.fr/fr/france-2030/france-2030/) under Grant Reference no. ANR-21-ESRE-0005, as well as from other contributors listed below. Its goal is provide researchers in the humanities with an integrated set of tools to transcribe, annotate, translate and publish historical documents.
The eScriptorium app itself is at the 'center'. It is a work in progress but will implement at least automatic transcriptions through kraken, indexation for complex search and filtering, annotation and some simple forms of collaborative working such as sharing and versioning.

## The stack
- nginx
- uwsgi
- [django](https://www.djangoproject.com/)
- [daphne](https://github.com/django/daphne) (channel server for websockets)
- [celery](http://www.celeryproject.org/)
- postgres
- [elasticsearch](https://www.elastic.co/)
- redis (cache, celery broker, other disposable data)
- [kraken](http://kraken.re)
- [docker](https://www.docker.com/) (deployment)


## Install
Two options,
- [install with Docker](https://gitlab.com/scripta/escriptorium/-/wikis/docker-install), or a
- [full local install](https://gitlab.com/scripta/escriptorium/-/wikis/full-install).

eScriptorium needs either Linux, macOS or Windows (with WSL).


## Contributing
See [Contributing to eScriptorium](https://gitlab.com/scripta/escriptorium/-/wikis/contributing).

## Current financial and technical contributors include:
- [École Pratique des Hautes Études (EPHE)](https://www.ephe.psl.eu)
- [Biblissima+](https://projet.biblissima.fr/)
- [Resilience](https://www.resilience-ri.eu/)
- [PSL Scripta](https://scripta.psl.eu/en/)
- [Institut national de recherche en sciences et technologies du numérique (INRIA)](https://inria.fr/en)
- [Archives nationales de France](https://www.archives-nationales.culture.gouv.fr/)
- [L’Institut de recherche et d’histoire des textes](https://www.irht.cnrs.fr/)
- [Open Islamicate Texts Initiative (OpenITI)](https://openiti.org/)
- [The Andrew W. Mellon Foundation](https://mellon.org/grants/)
