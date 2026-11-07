"""Explicit PR17 commercial assumptions; PR08 owns normalization and FX units."""
from odoo.exceptions import ValidationError
from .commercial_math import number

MODES=('original','explicit','fixed_discount','percent_discount','tier')

def decimal(value,positive=False):
    try:v=number(value,True)
    except ValueError as exc:raise ValidationError(str(exc)) from None
    if positive and v<=0:raise ValidationError('An explicit positive amount is required.')
    return v

def text(value,label):
    if not isinstance(value,str) or not value.strip() or len(value)>4000:
        raise ValidationError(label+' requires bounded nonempty evidence.')
    return value.strip()

def negotiated(proposal,old,mode,value=None,base='proposal'):
    if mode not in MODES:raise ValidationError('Choose one supported price method.')
    if mode=='original':
        if value is not None:raise ValidationError('Original proposal has no negotiated value.')
        return decimal(proposal)
    if mode=='tier':raise ValidationError('Tier prices require exact current PR08 row eligibility.')
    v=decimal(value)
    if mode=='explicit':return v
    if base not in ('proposal','old'):raise ValidationError('Select proposal or old discount base.')
    b=decimal(proposal if base=='proposal' else old)
    if mode=='percent_discount':
        if v>100:raise ValidationError('Discount must be between zero and100 percent.')
        return b*(1-v/100)
    if v>b:raise ValidationError('Per-unit discount cannot exceed its explicit base.')
    return b-v
