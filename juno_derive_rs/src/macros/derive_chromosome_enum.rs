use convert_case::{Case, Casing};
use proc_macro::TokenStream;
use quote::{format_ident, quote};
use syn::{parse_macro_input, ItemEnum};

pub fn derive_chromosome_enum(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as ItemEnum);

    let name_params = &input.ident;
    let name = format_ident!(
        "{}",
        name_params.to_string().strip_suffix("Params").unwrap()
    );

    let variant_name = input.variants.iter().map(|variant| &variant.ident);
    let variant_params_name = variant_name
        .clone()
        .map(|name| format_ident!("{}Params", name));
    let variant_len = input.variants.len();

    let construct_variant_name = variant_name.clone();
    let variant_len_variant_name = variant_name.clone();
    let variant_len_target_name = variant_params_name.clone();

    let ctx_name = format_ident!("{}Context", name_params);
    let ctx_variant_name = variant_name.clone();
    let ctx_target_name = variant_name
        .clone()
        .map(|name| format_ident!("{}ParamsContext", name));

    let ctx_default_ctx_name = variant_name.clone().map(|name| {
        format_ident!(
            "{}",
            format!("Default{}Ctx", name).to_case(Case::UpperSnake)
        )
    });
    let ctx_default_variant_ctx_name = ctx_target_name.clone();

    let ctx_impl_method_name = variant_name
        .clone()
        .map(|name| format_ident!("{}", name.to_string().to_lowercase()));
    let ctx_impl_method_target_name = ctx_target_name.clone();
    let ctx_impl_method_variant_name = variant_name.clone();
    let ctx_impl_method_default_ctx_name = ctx_default_ctx_name.clone();

    let len_variant_params_name = variant_params_name.clone();
    let generate_none_counter = 0..variant_len;
    let generate_none_variant_name = variant_name.clone();
    let generate_none_variant_params_name = variant_params_name.clone();
    let generate_none_default_ctx_name = ctx_default_ctx_name.clone();
    let generate_variant_name = variant_name.clone();
    let generate_variant_params_name = variant_params_name.clone();

    let cross_variant_name = variant_name.clone();

    let mutate_variant_name = variant_name.clone();
    let mutate_ctx_fn_name = ctx_impl_method_name.clone();

    let output = quote! {
        impl #name_params {
            pub fn construct(&self) -> Box<dyn #name> {
                match self {
                    #(
                        #name_params::#construct_variant_name(params) =>
                            Box::new(#construct_variant_name::new(params)),
                    )*
                    // TakeProfitParams::Basic(params) => Box::new(Basic::new(params)),
                }
            }

            pub fn variant_len(&self) -> usize {
                match self {
                    #(
                        #name_params::#variant_len_variant_name(_) =>
                            <#variant_len_target_name as Chromosome>::len(),
                    )*
                    // TakeProfitParams::Basic(_) => BasicParams::len(),
                }
            }
        }

        #[derive(Deserialize, Serialize)]
        #[serde(tag = "type")]
        pub enum #ctx_name {
            None,
            #(
                #ctx_variant_name(#ctx_target_name),
            )*
            // Basic(BasicParamsContext),
        }

        impl Default for #ctx_name {
            fn default() -> Self {
                #ctx_name::None
            }
        }

        #(
            static #ctx_default_ctx_name: once_cell::sync::Lazy<#ctx_default_variant_ctx_name> =
                once_cell::sync::Lazy::new(|| #ctx_default_variant_ctx_name::default());
        )*
        // static DEFAULT_BASIC_PARAMS_CTX: Lazy<BasicParamsContext> =
        //     Lazy::new(|| BasicParamsContext::default());

        impl #ctx_name {
            #(
                fn #ctx_impl_method_name(&self) -> &#ctx_impl_method_target_name {
                    match self {
                        #ctx_name::#ctx_impl_method_variant_name(ctx) => ctx,
                        _ => &#ctx_impl_method_default_ctx_name,
                    }
                }
            )*
        }
        // fn basic(&self) -> &BasicParamsContext {
        //     match self {
        //         TakeProfitParamsContext::Basic(ctx) => ctx,
        //         _ => &DEFAULT_BASIC_PARAMS_CTX,
        //     }
        // }

        impl Chromosome for #name_params {
            type Context = #ctx_name;

            fn len() -> usize {
                // 1 Extra is for a special slot which swaps the entire variant.
                1usize + [
                    #(<#len_variant_params_name as Chromosome>::len(),)*
                ].iter().max().unwrap()
            }

            fn generate(rng: &mut rand::prelude::StdRng, ctx: &Self::Context) -> Self {
                match ctx {
                    #ctx_name::None => match rand::Rng::gen_range(rng, 0..#variant_len) {
                        #(
                            #generate_none_counter => #name_params::#generate_none_variant_name(
                                #generate_none_variant_params_name::generate(rng, &#generate_none_default_ctx_name)
                            ),
                        )*
                        // 0 => TakeProfitParams::Basic(BasicParams::generate(rng, &DEFAULT_BASIC_PARAMS_CTX)),
                        _ => panic!(),
                    },
                    #(
                        #ctx_name::#generate_variant_name(ctx) => #name_params::#generate_variant_name(
                            #generate_variant_params_name::generate(rng, ctx)
                        ),
                    )*
                    // TakeProfitParamsContext::Basic(ctx) => {
                    //     TakeProfitParams::Basic(BasicParams::generate(rng, ctx))
                    // }
                    _ => panic!(),
                }
            }

            fn cross(&mut self, other: &mut Self, i: usize) {
                if i == 0 {
                    std::mem::swap(self, other);
                } else if std::mem::discriminant(self) == std::mem::discriminant(other) {
                    let i = i - 1;
                    if i < self.variant_len() {
                        match (self, other) {
                            #(
                                (
                                    #name_params::#cross_variant_name(left),
                                    #name_params::#cross_variant_name(right)
                                ) => left.cross(right, i),
                            )*
                            // (TakeProfitParams::Basic(left), TakeProfitParams::Basic(right)) => {
                            //     left.cross(right, i)
                            // }
                            _ => panic!(),
                        }
                    }
                }
            }

            fn mutate(&mut self, rng: &mut rand::prelude::StdRng, i: usize, ctx: &Self::Context) {
                if i == 0 {
                    *self = Self::generate(rng, ctx);
                } else {
                    let i = i - 1;
                    if i < self.variant_len() {
                        match self {
                            #(
                                #name_params::#mutate_variant_name(params) =>
                                    params.mutate(rng, i, ctx.#mutate_ctx_fn_name()),
                            )*
                            // TakeProfitParams::Basic(params) => params.mutate(rng, i, ctx.basic()),
                        }
                    }
                }
            }
        }
    };

    TokenStream::from(output)
}
