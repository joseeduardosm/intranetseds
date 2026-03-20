# Changelog

## 2026-03-20

### Sala de Situacao V2
- adicionada a configuracao `dia_referencia_monitoramento` por variavel matematica, com migration e ressincronizacao dos indicadores existentes;
- garantido ciclo inicial de monitoramento para toda variavel, com prazos mensais calculados pelo dia de referencia;
- ordenada a lista de entregas por `data_entrega_estipulada`;
- adicionada a visualizacao em calendario na tela `/sala-de-situacao/entregas/`;
- adicionados testes cobrindo ciclo inicial, prazo por referencia, ordenacao da lista e API de calendario.
